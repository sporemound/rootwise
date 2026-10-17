package org.rootwise.android.viewer

import org.rootwise.android.core.db.InventoryDatabase
import org.rootwise.android.core.db.JdbcSqliteDriver
import org.rootwise.android.core.db.SqliteConnection
import org.rootwise.android.core.db.SqliteDriver
import org.rootwise.android.core.model.RootwiseException
import java.io.Closeable
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.text.Normalizer

class InventoryReadException(message: String, cause: Throwable? = null) : RootwiseException(message, cause)

data class SessionSummary(
    val scanSessionId: String,
    val state: String,
    val sourceRoot: String,
    val startedAt: String,
    val finishedAt: String?,
    val observedCount: Long,
    val errorCount: Long
)

data class InventoryItem(
    val kind: String,
    val relativePath: String,
    val parentPath: String?,
    val name: String,
    val extension: String,
    val logicalBytes: Long,
    val modifiedNs: Long?,
    val depth: Int,
    val displayPath: String,
    val observationStatus: String
)

enum class SortField(val sqlExpression: String) {
    PATH("comparison_path COLLATE NOCASE"),
    SIZE("logical_bytes"),
    MODIFIED("COALESCE(modified_ns, 0)"),
    DEPTH("depth")
}

enum class SortOrder(val sqlKeyword: String) {
    ASC("ASC"),
    DESC("DESC")
}

/**
 * Bounded, query-only access to completed Rootwise inventories.
 * Port of `src/rootwise/viewer/inventory.py`.
 * Never opens or tests live source paths.
 */
class InventoryReader(
    inventoryPath: Path,
    driver: SqliteDriver = JdbcSqliteDriver
) : Closeable {
    val path: Path
    private val connection: SqliteConnection

    init {
        if (!Files.exists(inventoryPath, LinkOption.NOFOLLOW_LINKS) ||
            !Files.isRegularFile(inventoryPath, LinkOption.NOFOLLOW_LINKS)
        ) {
            throw InventoryReadException("inventory is not a file: $inventoryPath")
        }
        path = inventoryPath.toRealPath(LinkOption.NOFOLLOW_LINKS)
        val opened = driver.openReadOnly(path)
        try {
            opened.execute("PRAGMA query_only=ON")
            validate(opened)
            connection = opened
        } catch (t: Throwable) {
            try {
                opened.close()
            } catch (_: Throwable) {
            }
            if (t is InventoryReadException) throw t
            throw InventoryReadException("failed to open inventory read-only: ${t.message}", t)
        }
    }

    val isQueryOnly: Boolean
        get() = connection.pragmaInt("query_only") != 0

    private fun validate(conn: SqliteConnection) {
        val appId = conn.pragmaInt("application_id")
        if (appId != InventoryDatabase.INVENTORY_APPLICATION_ID) {
            throw InventoryReadException("inventory database application identity mismatch: $appId")
        }
        val required = setOf("scan_sessions", "files", "directories", "volumes")
        val present = conn.query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('directories','files','scan_sessions','volumes')"
        ) { it.getStringAt(0) ?: "" }.toSet()
        if (present != required) {
            throw InventoryReadException("inventory database schema is incomplete: $present")
        }
    }

    fun sessions(): List<SessionSummary> =
        connection.query(
            "SELECT scan_session_id,state,source_root,started_at,finished_at," +
                "observed_count,error_count FROM scan_sessions ORDER BY started_at,scan_session_id"
        ) { r ->
            SessionSummary(
                scanSessionId = r.getString("scan_session_id") ?: "",
                state = r.getString("state") ?: "",
                sourceRoot = r.getString("source_root") ?: "",
                startedAt = r.getString("started_at") ?: "",
                finishedAt = r.getString("finished_at"),
                observedCount = r.getLong("observed_count") ?: 0L,
                errorCount = r.getLong("error_count") ?: 0L
            )
        }

    fun latestCompleteSession(): String =
        connection.querySingleOrNull(
            "SELECT scan_session_id FROM scan_sessions WHERE state='COMPLETE' " +
                "ORDER BY finished_at DESC,started_at DESC,scan_session_id DESC LIMIT 1"
        ) { it.getStringAt(0) }
            ?: throw InventoryReadException("inventory has no COMPLETE scan session")

    private fun requireComplete(sessionId: String) {
        val state = connection.querySingleOrNull(
            "SELECT state FROM scan_sessions WHERE scan_session_id=?",
            listOf(sessionId)
        ) { it.getStringAt(0) }
            ?: throw InventoryReadException("scan session does not exist: $sessionId")
        if (state != "COMPLETE") {
            throw InventoryReadException("viewer search requires a COMPLETE scan session (got $state)")
        }
    }

    fun search(
        sessionId: String,
        query: String = "",
        kind: String? = null,
        limit: Int = 200,
        offset: Int = 0,
        sortField: SortField = SortField.PATH,
        sortOrder: SortOrder = SortOrder.ASC
    ): List<InventoryItem> {
        require(limit in 1..500) { "limit must be between 1 and 500" }
        require(offset >= 0) { "offset must be nonnegative" }
        require(kind == null || kind == "file" || kind == "directory") {
            "kind must be file, directory, or omitted"
        }
        requireComplete(sessionId)
        val normalized = Normalizer.normalize(query.trim(), Normalizer.Form.NFC)
        val escaped = normalized
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        val pattern = "%$escaped%"

        val orderClause = "${sortField.sqlExpression} ${sortOrder.sqlKeyword}, kind ASC, relative_path COLLATE BINARY ASC"
        val sql = buildString {
            append("WITH items AS (")
            append("SELECT scan_session_id,'directory' AS kind,relative_path,comparison_path,parent_path,")
            append("name,'' AS extension,logical_bytes,modified_ns,depth,display_path,observation_status ")
            append("FROM directories UNION ALL ")
            append("SELECT scan_session_id,'file' AS kind,relative_path,comparison_path,parent_path,")
            append("name,extension,logical_bytes,modified_ns,depth,display_path,observation_status FROM files")
            append(") SELECT kind,relative_path,parent_path,name,extension,logical_bytes,modified_ns,depth,")
            append("display_path,observation_status FROM items WHERE scan_session_id=? ")
            append("AND comparison_path LIKE ? ESCAPE '\\' COLLATE NOCASE ")
            if (kind != null) {
                append("AND kind=? ")
            }
            append("ORDER BY $orderClause LIMIT ? OFFSET ?")
        }
        val args = if (kind != null) {
            listOf(sessionId, pattern, kind, limit, offset)
        } else {
            listOf(sessionId, pattern, limit, offset)
        }
        return connection.query(sql, args) { r ->
            InventoryItem(
                kind = r.getString("kind") ?: "",
                relativePath = r.getString("relative_path") ?: "",
                parentPath = r.getString("parent_path"),
                name = r.getString("name") ?: "",
                extension = r.getString("extension") ?: "",
                logicalBytes = r.getLong("logical_bytes") ?: 0L,
                modifiedNs = r.getLong("modified_ns"),
                depth = r.getInt("depth") ?: 0,
                displayPath = r.getString("display_path") ?: "",
                observationStatus = r.getString("observation_status") ?: ""
            )
        }
    }

    fun item(sessionId: String, relativePath: String): InventoryItem? {
        requireComplete(sessionId)
        return connection.querySingleOrNull(
            "SELECT 'directory' AS kind,relative_path,parent_path,name,'' AS extension,logical_bytes," +
                "modified_ns,depth,display_path,observation_status FROM directories " +
                "WHERE scan_session_id=? AND relative_path=? UNION ALL " +
                "SELECT 'file' AS kind,relative_path,parent_path,name,extension,logical_bytes,modified_ns," +
                "depth,display_path,observation_status FROM files " +
                "WHERE scan_session_id=? AND relative_path=? LIMIT 1",
            listOf(sessionId, relativePath, sessionId, relativePath)
        ) { r ->
            InventoryItem(
                kind = r.getString("kind") ?: "",
                relativePath = r.getString("relative_path") ?: "",
                parentPath = r.getString("parent_path"),
                name = r.getString("name") ?: "",
                extension = r.getString("extension") ?: "",
                logicalBytes = r.getLong("logical_bytes") ?: 0L,
                modifiedNs = r.getLong("modified_ns"),
                depth = r.getInt("depth") ?: 0,
                displayPath = r.getString("display_path") ?: "",
                observationStatus = r.getString("observation_status") ?: ""
            )
        }
    }

    override fun close() {
        connection.close()
    }
}
