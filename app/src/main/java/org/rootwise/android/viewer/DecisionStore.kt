package org.rootwise.android.viewer

import org.rootwise.android.core.db.JdbcSqliteDriver
import org.rootwise.android.core.db.SqliteConnection
import org.rootwise.android.core.db.SqliteDriver
import org.rootwise.android.core.model.JsonCanonicalizer
import org.rootwise.android.core.model.RootwiseException
import java.io.Closeable
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path

class DecisionConflictException(message: String) : RootwiseException(message)

data class DecisionRecord(
    val scanSessionId: String,
    val relativePath: String,
    val decision: String,
    val note: String,
    val revision: Int,
    val recordedAt: String
)

/**
 * Separate, revision-checked, append-audited user decision storage.
 * Verbatim schema port of `src/rootwise/viewer/decisions.py`.
 */
class DecisionStore(
    decisionPath: Path,
    inventoryPath: Path,
    driver: SqliteDriver = JdbcSqliteDriver
) : Closeable {
    val path: Path
    private val connection: SqliteConnection

    init {
        if (!Files.exists(inventoryPath, LinkOption.NOFOLLOW_LINKS)) {
            throw IllegalArgumentException("inventory database does not exist: $inventoryPath")
        }
        val resolvedInventory = inventoryPath.toRealPath(LinkOption.NOFOLLOW_LINKS)
        val parent = decisionPath.toAbsolutePath().parent
            ?: throw IllegalArgumentException("decision database path has no parent: $decisionPath")
        val resolvedParent = parent.toRealPath(LinkOption.NOFOLLOW_LINKS)
        val resolvedDecision = resolvedParent.resolve(decisionPath.fileName)

        require(resolvedDecision != resolvedInventory) {
            "decision database must be distinct from the inventory database"
        }
        require(resolvedParent == resolvedInventory.parent) {
            "decision database must remain in the inventory database's external directory"
        }
        path = resolvedDecision
        val existed = Files.exists(path, LinkOption.NOFOLLOW_LINKS)
        val opened = driver.openReadWrite(path)
        try {
            val appId = opened.pragmaInt("application_id")
            if (existed && appId != DECISION_APPLICATION_ID) {
                throw IllegalArgumentException("decision database application identity mismatch: $appId")
            }
            opened.execute("PRAGMA journal_mode=DELETE")
            opened.execute("PRAGMA synchronous=FULL")
            opened.executeScript(SCHEMA)
            connection = opened
        } catch (t: Throwable) {
            try {
                opened.close()
            } catch (_: Throwable) {
            }
            throw t
        }
    }

    fun current(sessionId: String, relativePath: String): DecisionRecord? {
        val subject = validateSubject(sessionId, relativePath)
        return connection.querySingleOrNull(
            "SELECT scan_session_id,relative_path,decision,note,revision,updated_at AS recorded_at " +
                "FROM current_decisions WHERE scan_session_id=? AND relative_path=?",
            listOf(sessionId, subject)
        ) { r ->
            DecisionRecord(
                scanSessionId = r.getString("scan_session_id") ?: "",
                relativePath = r.getString("relative_path") ?: "",
                decision = r.getString("decision") ?: "",
                note = r.getString("note") ?: "",
                revision = r.getInt("revision") ?: 1,
                recordedAt = r.getString("recorded_at") ?: ""
            )
        }
    }

    fun currentForPaths(sessionId: String, relativePaths: List<String>): Map<String, DecisionRecord> {
        validateSubject(sessionId, "")
        require(relativePaths.size <= 500) { "decision page must contain at most 500 paths" }
        val subjects = relativePaths.map { validateSubject(sessionId, it) }.distinct()
        if (subjects.isEmpty()) return emptyMap()
        val placeholders = subjects.joinToString(",") { "?" }
        val rows = connection.query(
            "SELECT scan_session_id,relative_path,decision,note,revision,updated_at AS recorded_at " +
                "FROM current_decisions WHERE scan_session_id=? AND relative_path IN ($placeholders)",
            listOf(sessionId) + subjects
        ) { r ->
            DecisionRecord(
                scanSessionId = r.getString("scan_session_id") ?: "",
                relativePath = r.getString("relative_path") ?: "",
                decision = r.getString("decision") ?: "",
                note = r.getString("note") ?: "",
                revision = r.getInt("revision") ?: 1,
                recordedAt = r.getString("recorded_at") ?: ""
            )
        }
        return rows.associateBy { it.relativePath }
    }

    fun allCurrentDecisions(sessionId: String): List<DecisionRecord> {
        validateSubject(sessionId, "")
        return connection.query(
            "SELECT scan_session_id,relative_path,decision,note,revision,updated_at AS recorded_at " +
                "FROM current_decisions WHERE scan_session_id=? ORDER BY relative_path COLLATE BINARY",
            listOf(sessionId)
        ) { r ->
            DecisionRecord(
                scanSessionId = r.getString("scan_session_id") ?: "",
                relativePath = r.getString("relative_path") ?: "",
                decision = r.getString("decision") ?: "",
                note = r.getString("note") ?: "",
                revision = r.getInt("revision") ?: 1,
                recordedAt = r.getString("recorded_at") ?: ""
            )
        }
    }

    fun history(sessionId: String, relativePath: String): List<DecisionRecord> {
        val subject = validateSubject(sessionId, relativePath)
        return connection.query(
            "SELECT scan_session_id,relative_path,decision,note,revision,recorded_at " +
                "FROM decision_events WHERE scan_session_id=? AND relative_path=? ORDER BY revision",
            listOf(sessionId, subject)
        ) { r ->
            DecisionRecord(
                scanSessionId = r.getString("scan_session_id") ?: "",
                relativePath = r.getString("relative_path") ?: "",
                decision = r.getString("decision") ?: "",
                note = r.getString("note") ?: "",
                revision = r.getInt("revision") ?: 1,
                recordedAt = r.getString("recorded_at") ?: ""
            )
        }
    }

    fun setDecision(
        sessionId: String,
        relativePath: String,
        decision: String,
        note: String = "",
        expectedRevision: Int? = null
    ): DecisionRecord {
        val subject = validateSubject(sessionId, relativePath)
        require(decision in DECISIONS) { "unsupported decision: $decision" }
        require(note.length <= 4_000 && !note.contains('\u0000')) {
            "decision note must contain at most 4000 characters and no NUL"
        }
        return connection.inTransaction(immediate = true) {
            val currentRow = connection.querySingleOrNull(
                "SELECT decision,revision FROM current_decisions WHERE scan_session_id=? AND relative_path=?",
                listOf(sessionId, subject)
            ) { r ->
                Pair(r.getString("decision") ?: "", r.getInt("revision") ?: 0)
            }
            val previous: String?
            val nextRevision: Int
            if (currentRow == null) {
                if (expectedRevision != null && expectedRevision != 0) {
                    throw DecisionConflictException("new decision expected revision must be 0 or omitted")
                }
                previous = null
                nextRevision = 1
            } else {
                if (expectedRevision != currentRow.second) {
                    throw DecisionConflictException(
                        "decision update requires expected revision ${currentRow.second}"
                    )
                }
                previous = currentRow.first
                nextRevision = currentRow.second + 1
            }
            val recordedAt = JsonCanonicalizer.utcNowIsoSeconds()
            connection.execute(
                "INSERT INTO current_decisions VALUES(?,?,?,?,?,?) " +
                    "ON CONFLICT(scan_session_id,relative_path) DO UPDATE SET " +
                    "decision=excluded.decision,note=excluded.note,revision=excluded.revision," +
                    "updated_at=excluded.updated_at",
                listOf(sessionId, subject, decision, note, nextRevision, recordedAt)
            )
            connection.execute(
                "INSERT INTO decision_events(scan_session_id,relative_path,previous_decision," +
                    "decision,note,revision,recorded_at) VALUES(?,?,?,?,?,?,?)",
                listOf(sessionId, subject, previous, decision, note, nextRevision, recordedAt)
            )
            DecisionRecord(
                scanSessionId = sessionId,
                relativePath = subject,
                decision = decision,
                note = note,
                revision = nextRevision,
                recordedAt = recordedAt
            )
        }
    }

    override fun close() {
        connection.close()
    }

    companion object {
        const val DECISION_APPLICATION_ID = 1_346_654_807

        val DECISIONS = setOf(
            "KEEP",
            "PROTECT",
            "ARCHIVE_ELIGIBLE",
            "REBUILDABLE",
            "NOT_REBUILDABLE",
            "PROJECT_BOUNDARY",
            "NOT_A_PROJECT",
            "EXCLUDE_FROM_ANALYSIS",
            "UNKNOWN"
        )

        val SCHEMA = """
            PRAGMA application_id=1346654807;
            CREATE TABLE IF NOT EXISTS current_decisions (
              scan_session_id TEXT NOT NULL,
              relative_path TEXT NOT NULL,
              decision TEXT NOT NULL,
              note TEXT NOT NULL,
              revision INTEGER NOT NULL CHECK(revision >= 1),
              updated_at TEXT NOT NULL,
              PRIMARY KEY(scan_session_id, relative_path)
            );
            CREATE TABLE IF NOT EXISTS decision_events (
              event_id INTEGER PRIMARY KEY,
              scan_session_id TEXT NOT NULL,
              relative_path TEXT NOT NULL,
              previous_decision TEXT,
              decision TEXT NOT NULL,
              note TEXT NOT NULL,
              revision INTEGER NOT NULL CHECK(revision >= 1),
              recorded_at TEXT NOT NULL,
              UNIQUE(scan_session_id, relative_path, revision)
            );
            CREATE INDEX IF NOT EXISTS decision_events_subject
            ON decision_events(scan_session_id, relative_path, revision);
        """.trimIndent()

        fun validateSubject(sessionId: String, relativePath: String): String {
            if (sessionId.isEmpty() || sessionId.length > 128 || sessionId.contains('\u0000')) {
                throw IllegalArgumentException("scan session ID is invalid")
            }
            val normalized = relativePath.replace('\\', '/')
            if (normalized.contains('\u0000') || normalized.startsWith("/")) {
                throw IllegalArgumentException("decision subject must be a relative inventory path")
            }
            if (normalized.isEmpty()) return ""
            val parts = normalized.split('/').filter { it.isNotEmpty() }
            if (parts.any { it == "." || it == ".." }) {
                throw IllegalArgumentException("decision subject must be a normalized relative inventory path")
            }
            return parts.joinToString("/")
        }
    }
}
