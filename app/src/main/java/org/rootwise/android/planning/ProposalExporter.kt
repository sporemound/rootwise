package org.rootwise.android.planning

import org.rootwise.android.core.db.InventoryDatabase
import org.rootwise.android.core.db.JdbcSqliteDriver
import org.rootwise.android.core.db.SqliteConnection
import org.rootwise.android.core.db.SqliteDriver
import org.rootwise.android.core.model.JsonCanonicalizer
import org.rootwise.android.core.model.ScanStateException
import org.rootwise.android.viewer.DecisionStore
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.security.MessageDigest

data class ProposalAction(
    val candidateId: String,
    val relativePath: String,
    val action: String,
    val recursiveBytes: Long,
    val fileCount: Int,
    val proposedArchiveLabel: String?
) {
    fun toMap(): Map<String, Any?> = linkedMapOf(
        "action" to action,
        "candidate_id" to candidateId,
        "file_count" to fileCount,
        "proposed_archive_label" to proposedArchiveLabel,
        "recursive_bytes" to recursiveBytes,
        "relative_path" to relativePath
    )
}

data class ProposalExportResult(
    val proposalDigest: String,
    val scanSessionId: String,
    val inventoryLogicalDigest: String,
    val decisionsLogicalDigest: String,
    val actions: List<ProposalAction>,
    val jsonBytes: ByteArray
)

/**
 * Generates a non-executable storage planning proposal JSON from a completed
 * `inventory.db` snapshot and optional `decisions.db` store.
 *
 * Core Invariants Preserved:
 * - Opens `inventory.db` and `decisions.db` strictly read-only (`PRAGMA query_only = ON`).
 * - Never touches source paths or creates archives.
 * - Only directories with explicit `ARCHIVE_ELIGIBLE` decision and no protected
 *   ancestors/descendants (`KEEP`, `PROTECT`, `NOT_REBUILDABLE`) receive `ARCHIVE_AS_UNIT`.
 * - Archive roots never overlap (archived parent suppresses descendant `ARCHIVE_AS_UNIT`).
 * - Every authorization flag (`execution_authorized`, `archive_creation_authorized`,
 *   `original_removal_authorized`, `source_content_read_authorized`) is hardcoded `false`.
 */
object ProposalExporter {
    const val PROPOSAL_SCHEMA_VERSION = "rootwise-android-proposal-1"
    const val CODE_VERSION = "0.1.0-alpha"

    private val PROTECTED_DECISIONS = setOf("KEEP", "PROTECT", "NOT_REBUILDABLE")

    fun buildProposal(
        inventoryPath: Path,
        decisionsPath: Path?,
        sessionId: String? = null,
        driver: SqliteDriver = JdbcSqliteDriver
    ): ProposalExportResult {
        val realInventory = inventoryPath.toRealPath(LinkOption.NOFOLLOW_LINKS)
        val invConn = driver.openReadOnly(realInventory)
        try {
            invConn.execute("PRAGMA query_only=ON")
            if (invConn.pragmaInt("application_id") != InventoryDatabase.INVENTORY_APPLICATION_ID) {
                throw ScanStateException("inventory database application identity mismatch")
            }
            val resolvedSessionId = sessionId ?: invConn.querySingleOrNull(
                "SELECT scan_session_id FROM scan_sessions WHERE state='COMPLETE' " +
                    "ORDER BY finished_at DESC,started_at DESC,scan_session_id DESC LIMIT 1"
            ) { it.getStringAt(0) }
                ?: throw ScanStateException("proposal requires a COMPLETE scan session")

            val sessionRow = invConn.querySingleOrNull(
                "SELECT state,source_root FROM scan_sessions WHERE scan_session_id=?",
                listOf(resolvedSessionId)
            ) { r -> Pair(r.getStringAt(0) ?: "", r.getStringAt(1) ?: "") }
                ?: throw ScanStateException("scan session does not exist: $resolvedSessionId")

            if (sessionRow.first != "COMPLETE") {
                throw ScanStateException("proposal requires a COMPLETE scan session")
            }

            val inventoryDigest = computeInventoryLogicalDigest(invConn, resolvedSessionId)
            val decisionsMap = linkedMapOf<String, String>()
            val decisionsDigest: String
            if (decisionsPath != null && Files.exists(decisionsPath, LinkOption.NOFOLLOW_LINKS)) {
                val realDecisions = decisionsPath.toRealPath(LinkOption.NOFOLLOW_LINKS)
                val decConn = driver.openReadOnly(realDecisions)
                try {
                    decConn.execute("PRAGMA query_only=ON")
                    if (decConn.pragmaInt("application_id") != DecisionStore.DECISION_APPLICATION_ID) {
                        throw ScanStateException("decision database application identity mismatch")
                    }
                    val digest = MessageDigest.getInstance("SHA-256")
                    val rows = decConn.query(
                        "SELECT relative_path,decision,note,revision,updated_at FROM current_decisions " +
                            "WHERE scan_session_id=? ORDER BY relative_path COLLATE BINARY",
                        listOf(resolvedSessionId)
                    ) { r ->
                        val rel = r.getStringAt(0) ?: ""
                        val dec = r.getStringAt(1) ?: ""
                        val note = r.getStringAt(2) ?: ""
                        val rev = r.getIntAt(3) ?: 1
                        val updated = r.getStringAt(4) ?: ""
                        decisionsMap[rel] = dec
                        listOf(rel, dec, note, rev, updated)
                    }
                    for (r in rows) {
                        digest.update(JsonCanonicalizer.toCanonicalJsonLineBytes(r))
                    }
                    decisionsDigest = digest.digest().joinToString("") { "%02x".format(it) }
                } finally {
                    decConn.close()
                }
            } else {
                decisionsDigest = JsonCanonicalizer.sha256Hex(ByteArray(0))
            }

            val directories = invConn.query(
                "SELECT relative_path FROM directories WHERE scan_session_id=? " +
                    "AND entry_type='DIRECTORY' ORDER BY relative_path COLLATE BINARY",
                listOf(resolvedSessionId)
            ) { it.getStringAt(0) ?: "" }

            val files = invConn.query(
                "SELECT relative_path,logical_bytes FROM files WHERE scan_session_id=? " +
                    "AND entry_type='FILE' ORDER BY relative_path COLLATE BINARY",
                listOf(resolvedSessionId)
            ) { r -> Pair(r.getStringAt(0) ?: "", r.getLongAt(1) ?: 0L) }

            val errorPaths = invConn.query(
                "SELECT relative_path FROM scan_errors WHERE scan_session_id=? ORDER BY relative_path",
                listOf(resolvedSessionId)
            ) { it.getStringAt(0) ?: "" }

            val actions = computeCandidateActions(directories, files, errorPaths, decisionsMap)
            val totalEligibleBytes = actions
                .filter { it.action == "ARCHIVE_AS_UNIT" }
                .sumOf { it.recursiveBytes }
            val totalFiles = files.size
            val archivedFiles = actions
                .filter { it.action == "ARCHIVE_AS_UNIT" }
                .sumOf { it.fileCount }

            val payload = linkedMapOf<String, Any?>(
                "approval_state" to "UNAPPROVED",
                "authorizations" to linkedMapOf(
                    "archive_creation_authorized" to false,
                    "execution_authorized" to false,
                    "original_removal_authorized" to false,
                    "source_content_read_authorized" to false
                ),
                "code_version" to CODE_VERSION,
                "limitations" to listOf(
                    "DIRECTORY_ACTIONS_ARE_NOT_AN_ENUMERATED_ARCHIVE_MEMBER_MANIFEST",
                    "SOURCE_OBSERVATIONS_MUST_BE_REVALIDATED_BY_A_FUTURE_SEPARATE_COMPONENT",
                    "PROPOSED_ARCHIVE_NAMES_ARE_LABELS_ONLY"
                ),
                "plan" to linkedMapOf(
                    "actions" to actions.map { it.toMap() },
                    "objectives" to linkedMapOf(
                        "archive_count" to actions.count { it.action == "ARCHIVE_AS_UNIT" }.toDouble(),
                        "negative_recoverable_bytes" to (-totalEligibleBytes.toDouble()),
                        "remaining_loose_files" to (totalFiles - archivedFiles).toDouble()
                    )
                ),
                "schema_version" to PROPOSAL_SCHEMA_VERSION,
                "source" to linkedMapOf(
                    "decisions_digest" to decisionsDigest,
                    "inventory_filename" to realInventory.fileName.toString(),
                    "inventory_logical_digest" to inventoryDigest,
                    "recorded_source_root" to sessionRow.second,
                    "scan_session_id" to resolvedSessionId
                ),
                "state" to "PROPOSAL_ONLY_NON_EXECUTABLE"
            )

            val proposalDigest = JsonCanonicalizer.sha256HexOfCanonical(payload)
            payload["proposal_digest"] = proposalDigest
            val jsonBytes = JsonCanonicalizer.toCanonicalJsonLineBytes(payload)

            return ProposalExportResult(
                proposalDigest = proposalDigest,
                scanSessionId = resolvedSessionId,
                inventoryLogicalDigest = inventoryDigest,
                decisionsLogicalDigest = decisionsDigest,
                actions = actions,
                jsonBytes = jsonBytes
            )
        } finally {
            invConn.close()
        }
    }

    private fun computeInventoryLogicalDigest(conn: SqliteConnection, sessionId: String): String {
        val digest = MessageDigest.getInstance("SHA-256")
        val rows = conn.query(
            "SELECT kind,relative_path,parent_path,name,extension,logical_bytes,depth FROM (" +
                "SELECT 'directory' AS kind,relative_path,parent_path,name,'' AS extension,logical_bytes,depth " +
                "FROM directories WHERE scan_session_id=? UNION ALL " +
                "SELECT 'file' AS kind,relative_path,parent_path,name,extension,logical_bytes,depth " +
                "FROM files WHERE scan_session_id=?) ORDER BY relative_path COLLATE BINARY,kind",
            listOf(sessionId, sessionId)
        ) { r ->
            linkedMapOf<String, Any?>(
                "depth" to (r.getIntAt(6) ?: 0),
                "extension" to (r.getStringAt(4) ?: ""),
                "kind" to (r.getStringAt(0) ?: ""),
                "logical_bytes" to (r.getLongAt(5) ?: 0L),
                "name" to (r.getStringAt(3) ?: ""),
                "parent_path" to r.getStringAt(2),
                "relative_path" to (r.getStringAt(1) ?: "")
            )
        }
        for (row in rows) {
            digest.update(JsonCanonicalizer.toCanonicalJsonLineBytes(row))
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    private fun computeCandidateActions(
        directories: List<String>,
        files: List<Pair<String, Long>>,
        errorPaths: List<String>,
        decisions: Map<String, String>
    ): List<ProposalAction> {
        val actions = mutableListOf<ProposalAction>()
        val selectedArchiveRoots = mutableListOf<String>()

        for ((index, dirPath) in directories.withIndex()) {
            val candidateId = String.format(java.util.Locale.ROOT, "cand-%04d", index + 1)
            val memberFiles = files.filter { (filePath, _) -> isUnder(filePath, dirPath) }
            val recursiveBytes = memberFiles.sumOf { it.second }
            val fileCount = memberFiles.size

            val hasErrorIntersection = errorPaths.any { err ->
                err.isNotEmpty() && (isUnder(err, dirPath) || isUnder(dirPath, err))
            }
            val isProtected = decisions.entries.any { (decPath, dec) ->
                dec in PROTECTED_DECISIONS && (isUnder(decPath, dirPath) || isUnder(dirPath, decPath))
            }
            val alreadyCoveredByArchivedAncestor = selectedArchiveRoots.any { root ->
                isUnder(dirPath, root)
            }
            val decision = decisions[dirPath]

            val action: String
            val archiveLabel: String?
            when {
                isProtected -> {
                    action = "PROTECTED"
                    archiveLabel = null
                }
                alreadyCoveredByArchivedAncestor -> {
                    action = "KEEP_UNPACKED"
                    archiveLabel = null
                }
                decision == "ARCHIVE_ELIGIBLE" && !hasErrorIntersection && fileCount > 0 -> {
                    val hasEligibleChild = decisions.entries.any { (otherPath, otherDec) ->
                        otherPath != dirPath && isUnder(otherPath, dirPath) && otherDec == "ARCHIVE_ELIGIBLE"
                    }
                    if (hasEligibleChild && decision != "ARCHIVE_ELIGIBLE") {
                        action = "DEFER_TO_CHILDREN"
                        archiveLabel = null
                    } else {
                        action = "ARCHIVE_AS_UNIT"
                        val slug = dirPath.replace('/', '_').replace(Regex("[^A-Za-z0-9._-]"), "_")
                        archiveLabel = "proposal-$candidateId-$slug.zip"
                        selectedArchiveRoots.add(dirPath)
                    }
                }
                decisions.entries.any { (otherPath, otherDec) ->
                    otherPath != dirPath && isUnder(otherPath, dirPath) && otherDec == "ARCHIVE_ELIGIBLE"
                } -> {
                    action = "DEFER_TO_CHILDREN"
                    archiveLabel = null
                }
                else -> {
                    action = "KEEP_UNPACKED"
                    archiveLabel = null
                }
            }

            actions.add(
                ProposalAction(
                    candidateId = candidateId,
                    relativePath = dirPath,
                    action = action,
                    recursiveBytes = recursiveBytes,
                    fileCount = fileCount,
                    proposedArchiveLabel = archiveLabel
                )
            )
        }
        return actions
    }

    private fun isUnder(path: String, root: String): Boolean =
        root.isEmpty() || path == root || path.startsWith("$root/")
}
