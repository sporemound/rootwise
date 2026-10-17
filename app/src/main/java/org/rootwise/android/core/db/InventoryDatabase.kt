package org.rootwise.android.core.db

import org.rootwise.android.core.guard.WriteGuard
import org.rootwise.android.core.model.AdapterCapabilities
import org.rootwise.android.core.model.JsonCanonicalizer
import org.rootwise.android.core.model.Observation
import org.rootwise.android.core.model.ScanConfig
import org.rootwise.android.core.model.ScanErrorRecord
import org.rootwise.android.core.model.ScanStateException
import org.rootwise.android.core.model.SessionState
import org.rootwise.android.core.model.VolumeInfo
import java.io.Closeable
import java.nio.file.Path
import java.util.UUID

/**
 * External SQLite inventory and persisted scan frontier.
 * Verbatim schema port of `src/rootwise/database.py`.
 */
class InventoryDatabase(
    targetPath: Path,
    private val guard: WriteGuard,
    driver: SqliteDriver = JdbcSqliteDriver
) : Closeable {
    val path: Path = guard.authorize(targetPath)
    val journalPath: Path = guard.authorizeSqliteJournal(path)
    private val lease: WriteGuard.DatabaseLease = guard.openDatabaseLease(path)
    val connection: SqliteConnection

    init {
        var opened: SqliteConnection? = null
        try {
            opened = driver.openReadWrite(path)
            guard.verifyExisting(path)
            opened.execute("PRAGMA foreign_keys = ON")
            opened.execute("PRAGMA journal_mode = DELETE")
            opened.execute("PRAGMA synchronous = FULL")
            opened.execute("PRAGMA temp_store = MEMORY")
            opened.executeScript(SCHEMA)
            opened.inTransaction {
                opened.execute(
                    "INSERT INTO application_writes(scan_session_id,path,purpose,recorded_at) VALUES(NULL,?,?,?)",
                    listOf(path.toString(), "inventory_database", JsonCanonicalizer.utcNowIsoSeconds())
                )
            }
            connection = opened
        } catch (t: Throwable) {
            try {
                opened?.close()
            } catch (_: Throwable) {
            }
            lease.close()
            throw t
        }
    }

    fun startSession(
        volume: VolumeInfo,
        config: ScanConfig,
        sourceRoot: String,
        capabilities: AdapterCapabilities
    ): String {
        val sessionId = UUID.randomUUID().toString()
        val configJson = JsonCanonicalizer.toCanonicalJson(
            config.toConfigurationMap(capabilities, guard.separationMode)
        )
        val now = JsonCanonicalizer.utcNowIsoSeconds()
        connection.inTransaction {
            connection.execute(
                "INSERT OR IGNORE INTO volumes(identity,mount_path,filesystem_type,device) VALUES(?,?,?,?)",
                listOf(volume.identity, volume.mountPath, volume.filesystemType, volume.device)
            )
            val volumeId = connection.querySingleOrNull(
                "SELECT volume_id FROM volumes WHERE identity=?",
                listOf(volume.identity)
            ) { it.getLongAt(0) }
                ?: throw ScanStateException("failed to resolve volume_id for ${volume.identity}")

            connection.execute(
                "INSERT INTO scan_sessions(scan_session_id,volume_id,state,source_root,started_at,configuration_json) " +
                    "VALUES(?,?,?,?,?,?)",
                listOf(sessionId, volumeId, SessionState.RUNNING.wireValue, sourceRoot, now, configJson)
            )
            connection.execute(
                "INSERT INTO scan_frontier(scan_session_id,relative_path,state) VALUES(?,?,?)",
                listOf(sessionId, "", "PENDING")
            )
            connection.execute(
                "INSERT INTO scan_events(scan_session_id,event_type,detail_json,recorded_at) VALUES(?,?,?,?)",
                listOf(sessionId, "STARTED", "{}", now)
            )
        }
        return sessionId
    }

    fun resumeSession(volume: VolumeInfo, sourceRoot: String): String {
        validateDatabaseForResume()
        val row = connection.querySingleOrNull(
            "SELECT s.scan_session_id, s.state FROM scan_sessions s JOIN volumes v USING(volume_id) " +
                "WHERE v.identity=? AND s.source_root=? AND s.state IN ('RUNNING','STOPPED','FAILED') " +
                "ORDER BY s.started_at DESC LIMIT 1",
            listOf(volume.identity, sourceRoot)
        ) { r ->
            Pair(r.getStringAt(0) ?: "", r.getStringAt(1) ?: "")
        } ?: throw ScanStateException("no resumable session exists for source volume")

        val sessionId = row.first
        val previousState = row.second
        val eventType = if (previousState == "RUNNING") "RECOVERED_AFTER_CRASH" else "RESUMED"
        val now = JsonCanonicalizer.utcNowIsoSeconds()
        connection.inTransaction {
            connection.execute(
                "UPDATE scan_frontier SET state='PENDING' WHERE scan_session_id=? AND state='SCANNING'",
                listOf(sessionId)
            )
            connection.execute(
                "UPDATE scan_sessions SET state='RUNNING', finished_at=NULL WHERE scan_session_id=?",
                listOf(sessionId)
            )
            connection.execute(
                "INSERT INTO scan_events(scan_session_id,event_type,detail_json,recorded_at) VALUES(?,?,?,?)",
                listOf(sessionId, eventType, "{}", now)
            )
        }
        return sessionId
    }

    private fun validateDatabaseForResume() {
        val appId = connection.pragmaInt("application_id")
        if (appId != INVENTORY_APPLICATION_ID) {
            throw ScanStateException("database application identity mismatch before resume: $appId")
        }
        val integrity = connection.pragmaString("integrity_check")
        if (integrity != "ok") {
            throw ScanStateException("SQLite integrity check failed before resume: $integrity")
        }
        val fkViolation = connection.querySingleOrNull("PRAGMA foreign_key_check") { it.getStringAt(0) }
        if (fkViolation != null) {
            throw ScanStateException("SQLite foreign-key check failed before resume")
        }
    }

    fun nextDirectory(sessionId: String): String? =
        connection.querySingleOrNull(
            "SELECT relative_path FROM scan_frontier WHERE scan_session_id=? AND state='PENDING' " +
                "ORDER BY relative_path LIMIT 1",
            listOf(sessionId)
        ) { it.getStringAt(0) }

    fun commitDirectory(
        sessionId: String,
        relativePath: String,
        observations: List<Observation>,
        childDirectories: List<String>,
        errors: List<ScanErrorRecord>,
        done: Boolean = true
    ): Int {
        connection.inTransaction {
            connection.execute(
                "UPDATE scan_frontier SET state='SCANNING' WHERE scan_session_id=? AND relative_path=?",
                listOf(sessionId, relativePath)
            )
            for (item in observations) {
                val isDirTable = item.entryType == "DIRECTORY" || item.entryType == "SYMLINK_DIRECTORY"
                if (isDirTable) {
                    connection.execute(
                        "INSERT OR REPLACE INTO directories VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        listOf(
                            sessionId,
                            item.relativePath,
                            item.comparisonPath,
                            item.parentPath,
                            item.name,
                            item.entryType,
                            item.logicalBytes,
                            item.createdNs,
                            item.modifiedNs,
                            item.accessedNs,
                            item.attributes,
                            item.depth,
                            item.displayPath,
                            item.observationStatus
                        )
                    )
                } else {
                    connection.execute(
                        "INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        listOf(
                            sessionId,
                            item.relativePath,
                            item.comparisonPath,
                            item.parentPath,
                            item.name,
                            item.extension,
                            item.entryType,
                            item.logicalBytes,
                            item.createdNs,
                            item.modifiedNs,
                            item.accessedNs,
                            item.attributes,
                            item.depth,
                            item.displayPath,
                            item.observationStatus
                        )
                    )
                }
            }
            for (childPath in childDirectories) {
                connection.execute(
                    "INSERT OR IGNORE INTO scan_frontier(scan_session_id,relative_path,state) VALUES(?,?,'PENDING')",
                    listOf(sessionId, childPath)
                )
            }
            for (err in errors) {
                connection.execute(
                    "INSERT INTO scan_errors(scan_session_id,relative_path,operation,error_type,error_code,message) " +
                        "VALUES(?,?,?,?,?,?)",
                    listOf(sessionId, err.relativePath, err.operation, err.errorType, err.errorCode, err.message)
                )
            }
            if (done) {
                connection.execute(
                    "UPDATE scan_frontier SET state='DONE' WHERE scan_session_id=? AND relative_path=?",
                    listOf(sessionId, relativePath)
                )
            }
            connection.execute(
                "UPDATE scan_sessions SET observed_count=observed_count+?, error_count=error_count+? " +
                    "WHERE scan_session_id=?",
                listOf(observations.size, errors.size, sessionId)
            )
        }
        return observations.size
    }

    fun finish(sessionId: String, state: SessionState) {
        val current = connection.querySingleOrNull(
            "SELECT state FROM scan_sessions WHERE scan_session_id=?",
            listOf(sessionId)
        ) { it.getStringAt(0) }
        if (current == null || current != SessionState.RUNNING.wireValue) {
            throw ScanStateException("only a RUNNING session can finish")
        }
        if (state == SessionState.COMPLETE) {
            val pending = connection.querySingleOrNull(
                "SELECT COUNT(*) FROM scan_frontier WHERE scan_session_id=? AND state!='DONE'",
                listOf(sessionId)
            ) { it.getLongAt(0) ?: 0L } ?: 0L
            if (pending > 0L) {
                throw ScanStateException("a session with unfinished frontier work cannot be COMPLETE")
            }
        }
        val now = JsonCanonicalizer.utcNowIsoSeconds()
        connection.inTransaction {
            connection.execute(
                "UPDATE scan_sessions SET state=?, finished_at=?, " +
                    "observed_count=(SELECT COUNT(*) FROM files WHERE scan_session_id=?)+" +
                    "(SELECT COUNT(*) FROM directories WHERE scan_session_id=?), " +
                    "error_count=(SELECT COUNT(*) FROM scan_errors WHERE scan_session_id=?) " +
                    "WHERE scan_session_id=?",
                listOf(state.wireValue, now, sessionId, sessionId, sessionId, sessionId)
            )
            connection.execute(
                "INSERT INTO scan_events(scan_session_id,event_type,detail_json,recorded_at) VALUES(?,?,?,?)",
                listOf(sessionId, state.wireValue, "{}", now)
            )
        }
    }

    fun recordWrite(sessionId: String?, targetPath: Path, purpose: String) {
        connection.inTransaction {
            connection.execute(
                "INSERT INTO application_writes(scan_session_id,path,purpose,recorded_at) VALUES(?,?,?,?)",
                listOf(sessionId, targetPath.toString(), purpose, JsonCanonicalizer.utcNowIsoSeconds())
            )
        }
    }

    fun recordError(
        sessionId: String,
        relativePath: String,
        operation: String,
        errorType: String,
        errorCode: Int?,
        message: String
    ) {
        connection.inTransaction {
            connection.execute(
                "INSERT INTO scan_errors(scan_session_id,relative_path,operation,error_type,error_code,message) " +
                    "VALUES(?,?,?,?,?,?)",
                listOf(sessionId, relativePath, operation, errorType, errorCode, message)
            )
        }
    }

    fun recordEvent(sessionId: String, eventType: String, detail: Map<String, Any?>) {
        connection.inTransaction {
            connection.execute(
                "INSERT INTO scan_events(scan_session_id,event_type,detail_json,recorded_at) VALUES(?,?,?,?)",
                listOf(
                    sessionId,
                    eventType,
                    JsonCanonicalizer.toCanonicalJson(detail),
                    JsonCanonicalizer.utcNowIsoSeconds()
                )
            )
        }
    }

    override fun close() {
        try {
            connection.close()
        } finally {
            lease.close()
        }
    }

    companion object {
        const val INVENTORY_APPLICATION_ID = 1_346_654_806

        val SCHEMA = """
            PRAGMA foreign_keys = ON;
            PRAGMA application_id = 1346654806;
            CREATE TABLE IF NOT EXISTS volumes (
              volume_id INTEGER PRIMARY KEY,
              identity TEXT NOT NULL UNIQUE,
              mount_path TEXT NOT NULL,
              filesystem_type TEXT,
              device TEXT
            );
            CREATE TABLE IF NOT EXISTS scan_sessions (
              scan_session_id TEXT PRIMARY KEY,
              volume_id INTEGER NOT NULL REFERENCES volumes(volume_id),
              state TEXT NOT NULL CHECK(state IN ('RUNNING','COMPLETE','STOPPED','FAILED')),
              source_root TEXT NOT NULL,
              started_at TEXT NOT NULL,
              finished_at TEXT,
              configuration_json TEXT NOT NULL,
              observed_count INTEGER NOT NULL DEFAULT 0,
              error_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS directories (
              scan_session_id TEXT NOT NULL REFERENCES scan_sessions(scan_session_id),
              relative_path TEXT NOT NULL,
              comparison_path TEXT NOT NULL,
              parent_path TEXT,
              name TEXT NOT NULL,
              entry_type TEXT NOT NULL,
              logical_bytes INTEGER NOT NULL,
              created_ns INTEGER,
              modified_ns INTEGER,
              accessed_ns INTEGER,
              attributes INTEGER NOT NULL,
              depth INTEGER NOT NULL,
              display_path TEXT NOT NULL,
              observation_status TEXT NOT NULL,
              PRIMARY KEY(scan_session_id, relative_path)
            );
            CREATE TABLE IF NOT EXISTS files (
              scan_session_id TEXT NOT NULL REFERENCES scan_sessions(scan_session_id),
              relative_path TEXT NOT NULL,
              comparison_path TEXT NOT NULL,
              parent_path TEXT,
              name TEXT NOT NULL,
              extension TEXT NOT NULL,
              entry_type TEXT NOT NULL,
              logical_bytes INTEGER NOT NULL,
              created_ns INTEGER,
              modified_ns INTEGER,
              accessed_ns INTEGER,
              attributes INTEGER NOT NULL,
              depth INTEGER NOT NULL,
              display_path TEXT NOT NULL,
              observation_status TEXT NOT NULL,
              PRIMARY KEY(scan_session_id, relative_path)
            );
            CREATE TABLE IF NOT EXISTS scan_errors (
              error_id INTEGER PRIMARY KEY,
              scan_session_id TEXT NOT NULL REFERENCES scan_sessions(scan_session_id),
              relative_path TEXT NOT NULL,
              operation TEXT NOT NULL,
              error_type TEXT NOT NULL,
              error_code INTEGER,
              message TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS scan_frontier (
              scan_session_id TEXT NOT NULL REFERENCES scan_sessions(scan_session_id),
              relative_path TEXT NOT NULL,
              state TEXT NOT NULL CHECK(state IN ('PENDING','SCANNING','DONE')),
              PRIMARY KEY(scan_session_id, relative_path)
            );
            CREATE INDEX IF NOT EXISTS frontier_next ON scan_frontier(scan_session_id, state, relative_path);
            CREATE TABLE IF NOT EXISTS scan_events (
              event_id INTEGER PRIMARY KEY,
              scan_session_id TEXT NOT NULL REFERENCES scan_sessions(scan_session_id),
              event_type TEXT NOT NULL,
              detail_json TEXT NOT NULL,
              recorded_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS canonical_exports (
              export_id INTEGER PRIMARY KEY,
              scan_session_id TEXT NOT NULL REFERENCES scan_sessions(scan_session_id),
              output_path TEXT NOT NULL,
              sha256 TEXT NOT NULL,
              record_count INTEGER NOT NULL,
              completed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS application_writes (
              write_id INTEGER PRIMARY KEY,
              scan_session_id TEXT,
              path TEXT NOT NULL,
              purpose TEXT NOT NULL,
              recorded_at TEXT NOT NULL
            );
        """.trimIndent()
    }
}
