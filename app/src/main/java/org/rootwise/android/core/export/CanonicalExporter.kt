package org.rootwise.android.core.export

import org.rootwise.android.core.db.InventoryDatabase
import org.rootwise.android.core.db.SqliteConnection
import org.rootwise.android.core.guard.WriteGuard
import org.rootwise.android.core.model.JsonCanonicalizer
import org.rootwise.android.core.model.ScanStateException
import java.nio.file.Path
import java.security.MessageDigest

data class CanonicalExportResult(
    val sha256: String,
    val recordCount: Int,
    val outputPath: Path
)

/**
 * Streaming deterministic NDJSON export for completed inventory sessions.
 * Port of `src/rootwise/canonicalize.py`.
 */
object CanonicalExporter {
    fun exportCanonical(
        database: InventoryDatabase,
        guard: WriteGuard,
        sessionId: String,
        outputPath: Path
    ): CanonicalExportResult {
        val conn = database.connection
        val result = conn.inTransaction {
            validateSnapshot(conn, sessionId)
            val digest = MessageDigest.getInstance("SHA-256")
            var count = 0
            val writtenPath = guard.openNewBinary(outputPath) { destination, stream ->
                val header = JsonCanonicalizer.toCanonicalJsonLineBytes(
                    mapOf(
                        "record_type" to "session",
                        "schema" to 2,
                        "status" to "COMPLETE"
                    )
                )
                stream.write(header)
                digest.update(header)
                count += 1

                val dirRows = conn.query(
                    "SELECT relative_path,comparison_path,parent_path,name,entry_type,logical_bytes," +
                        "created_ns,modified_ns,accessed_ns,attributes,depth,display_path,observation_status " +
                        "FROM directories WHERE scan_session_id=? ORDER BY relative_path COLLATE BINARY",
                    listOf(sessionId)
                ) { row ->
                    linkedMapOf<String, Any?>(
                        "accessed_time" to JsonCanonicalizer.formatTimestampNs(row.getLong("accessed_ns")),
                        "attributes" to (row.getInt("attributes") ?: 0),
                        "comparison_path" to row.getString("comparison_path"),
                        "created_time" to JsonCanonicalizer.formatTimestampNs(row.getLong("created_ns")),
                        "depth" to (row.getInt("depth") ?: 0),
                        "display_path" to row.getString("display_path"),
                        "entry_type" to row.getString("entry_type"),
                        "logical_bytes" to (row.getLong("logical_bytes") ?: 0L),
                        "modified_time" to JsonCanonicalizer.formatTimestampNs(row.getLong("modified_ns")),
                        "name" to row.getString("name"),
                        "observation_status" to row.getString("observation_status"),
                        "parent_path" to row.getString("parent_path"),
                        "record_type" to "directory",
                        "relative_path" to row.getString("relative_path")
                    )
                }
                for (record in dirRows) {
                    val line = JsonCanonicalizer.toCanonicalJsonLineBytes(record)
                    stream.write(line)
                    digest.update(line)
                    count += 1
                }

                val fileRows = conn.query(
                    "SELECT relative_path,comparison_path,parent_path,name,extension,entry_type,logical_bytes," +
                        "created_ns,modified_ns,accessed_ns,attributes,depth,display_path,observation_status " +
                        "FROM files WHERE scan_session_id=? ORDER BY relative_path COLLATE BINARY",
                    listOf(sessionId)
                ) { row ->
                    linkedMapOf<String, Any?>(
                        "accessed_time" to JsonCanonicalizer.formatTimestampNs(row.getLong("accessed_ns")),
                        "attributes" to (row.getInt("attributes") ?: 0),
                        "comparison_path" to row.getString("comparison_path"),
                        "created_time" to JsonCanonicalizer.formatTimestampNs(row.getLong("created_ns")),
                        "depth" to (row.getInt("depth") ?: 0),
                        "display_path" to row.getString("display_path"),
                        "entry_type" to row.getString("entry_type"),
                        "extension" to row.getString("extension"),
                        "logical_bytes" to (row.getLong("logical_bytes") ?: 0L),
                        "modified_time" to JsonCanonicalizer.formatTimestampNs(row.getLong("modified_ns")),
                        "name" to row.getString("name"),
                        "observation_status" to row.getString("observation_status"),
                        "parent_path" to row.getString("parent_path"),
                        "record_type" to "file",
                        "relative_path" to row.getString("relative_path")
                    )
                }
                for (record in fileRows) {
                    val line = JsonCanonicalizer.toCanonicalJsonLineBytes(record)
                    stream.write(line)
                    digest.update(line)
                    count += 1
                }

                val errorRows = conn.query(
                    "SELECT relative_path,operation,error_type,error_code,message FROM scan_errors " +
                        "WHERE scan_session_id=? ORDER BY relative_path,operation,error_id",
                    listOf(sessionId)
                ) { row ->
                    linkedMapOf<String, Any?>(
                        "error_code" to row.getInt("error_code"),
                        "error_type" to row.getString("error_type"),
                        "message" to row.getString("message"),
                        "operation" to row.getString("operation"),
                        "record_type" to "error",
                        "relative_path" to row.getString("relative_path")
                    )
                }
                for (record in errorRows) {
                    val line = JsonCanonicalizer.toCanonicalJsonLineBytes(record)
                    stream.write(line)
                    digest.update(line)
                    count += 1
                }

                val eventRows = conn.query(
                    "SELECT event_type,detail_json FROM scan_events WHERE scan_session_id=? ORDER BY event_id",
                    listOf(sessionId)
                ) { row ->
                    Pair(row.getString("event_type") ?: "", row.getString("detail_json") ?: "{}")
                }
                for ((eventType, detailJson) in eventRows) {
                    val lineStr = "{\"detail\":$detailJson,\"event_type\":${JsonCanonicalizer.toCanonicalJson(eventType)},\"record_type\":\"event\"}\n"
                    val lineBytes = lineStr.toByteArray(Charsets.UTF_8)
                    stream.write(lineBytes)
                    digest.update(lineBytes)
                    count += 1
                }
                destination
            }

            val sha256Hex = digest.digest().joinToString("") { "%02x".format(it) }
            conn.execute(
                "INSERT INTO canonical_exports(scan_session_id,output_path,sha256,record_count,completed_at) " +
                    "VALUES(?,?,?,?,?)",
                listOf(sessionId, writtenPath.toString(), sha256Hex, count, JsonCanonicalizer.utcNowIsoSeconds())
            )
            CanonicalExportResult(sha256 = sha256Hex, recordCount = count, outputPath = writtenPath)
        }
        database.recordWrite(sessionId, result.outputPath, "canonical_ndjson")
        return result
    }

    fun validateSnapshot(conn: SqliteConnection, sessionId: String) {
        if (conn.pragmaInt("application_id") != InventoryDatabase.INVENTORY_APPLICATION_ID) {
            throw ScanStateException("database application identity mismatch")
        }
        if (conn.pragmaString("integrity_check") != "ok") {
            throw ScanStateException("SQLite integrity check failed")
        }
        val fkViolation = conn.querySingleOrNull("PRAGMA foreign_key_check") { it.getStringAt(0) }
        if (fkViolation != null) {
            throw ScanStateException("SQLite foreign-key consistency check failed")
        }
        val session = conn.querySingleOrNull(
            "SELECT state,observed_count,error_count FROM scan_sessions WHERE scan_session_id=?",
            listOf(sessionId)
        ) { r ->
            Triple(r.getStringAt(0) ?: "", r.getLongAt(1) ?: -1L, r.getLongAt(2) ?: -1L)
        } ?: throw ScanStateException("canonical export requires a COMPLETE session")

        if (session.first != "COMPLETE") {
            throw ScanStateException("canonical export requires a COMPLETE session")
        }
        val unfinished = conn.querySingleOrNull(
            "SELECT COUNT(*) FROM scan_frontier WHERE scan_session_id=? AND state!='DONE'",
            listOf(sessionId)
        ) { it.getLongAt(0) ?: 0L } ?: 0L
        val observed = conn.querySingleOrNull(
            "SELECT (SELECT COUNT(*) FROM files WHERE scan_session_id=?)+" +
                "(SELECT COUNT(*) FROM directories WHERE scan_session_id=?)",
            listOf(sessionId, sessionId)
        ) { it.getLongAt(0) ?: 0L } ?: 0L
        val errors = conn.querySingleOrNull(
            "SELECT COUNT(*) FROM scan_errors WHERE scan_session_id=?",
            listOf(sessionId)
        ) { it.getLongAt(0) ?: 0L } ?: 0L

        if (unfinished > 0L || observed != session.second || errors != session.third) {
            throw ScanStateException("completed session consistency validation failed")
        }
    }
}
