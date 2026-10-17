package org.rootwise.android.core.db

import java.io.Closeable
import java.nio.file.Path
import java.sql.Connection
import java.sql.DriverManager
import java.sql.PreparedStatement
import java.sql.Types

/**
 * Minimal zero-dependency SQLite connection abstraction so core scanner, viewer, and
 * planning logic use `android.database.sqlite.SQLiteDatabase` at Android runtime (0 external deps)
 * and standard `java.sql` JDBC SQLite during local JVM unit tests.
 */
interface SqliteRow {
    fun getString(column: String): String?
    fun getLong(column: String): Long?
    fun getInt(column: String): Int?
    fun getDouble(column: String): Double?
    fun getStringAt(index: Int): String?
    fun getLongAt(index: Int): Long?
    fun getIntAt(index: Int): Int?
}

interface SqliteConnection : Closeable {
    fun execute(sql: String, args: List<Any?> = emptyList())
    fun executeScript(sqlScript: String)
    fun <T> query(sql: String, args: List<Any?> = emptyList(), mapper: (SqliteRow) -> T): List<T>
    fun <T> querySingleOrNull(sql: String, args: List<Any?> = emptyList(), mapper: (SqliteRow) -> T): T?
    fun pragmaInt(name: String): Int
    fun pragmaString(name: String): String
    fun <T> inTransaction(immediate: Boolean = false, block: () -> T): T
}

interface SqliteDriver {
    fun openReadWrite(path: Path): SqliteConnection
    fun openReadOnly(path: Path): SqliteConnection
}

/**
 * Standard `java.sql` JDBC SQLite driver used by JVM unit tests.
 */
object JdbcSqliteDriver : SqliteDriver {
    override fun openReadWrite(path: Path): SqliteConnection {
        val url = "jdbc:sqlite:${path.toAbsolutePath()}"
        val conn = DriverManager.getConnection(url)
        return JdbcSqliteConnection(conn)
    }

    override fun openReadOnly(path: Path): SqliteConnection {
        val uriPath = path.toAbsolutePath().toString().replace('\\', '/')
        val url = "jdbc:sqlite:file:$uriPath?mode=ro"
        val prop = java.util.Properties().apply {
            setProperty("open_mode", "1") // SQLITE_OPEN_READONLY
        }
        val conn = DriverManager.getConnection(url, prop)
        return JdbcSqliteConnection(conn)
    }
}

private class JdbcSqliteConnection(private val conn: Connection) : SqliteConnection {
    override fun execute(sql: String, args: List<Any?>) {
        conn.prepareStatement(sql).use { stmt ->
            bindArgs(stmt, args)
            stmt.execute()
        }
    }

    override fun executeScript(sqlScript: String) {
        val statements = sqlScript
            .split(';')
            .map { it.trim() }
            .filter { it.isNotEmpty() }
        for (statement in statements) {
            conn.createStatement().use { stmt ->
                stmt.execute(statement)
            }
        }
    }

    override fun <T> query(sql: String, args: List<Any?>, mapper: (SqliteRow) -> T): List<T> {
        conn.prepareStatement(sql).use { stmt ->
            bindArgs(stmt, args)
            stmt.executeQuery().use { rs ->
                val results = mutableListOf<T>()
                val row = JdbcSqliteRow(rs)
                while (rs.next()) {
                    results.add(mapper(row))
                }
                return results
            }
        }
    }

    override fun <T> querySingleOrNull(sql: String, args: List<Any?>, mapper: (SqliteRow) -> T): T? {
        conn.prepareStatement(sql).use { stmt ->
            bindArgs(stmt, args)
            stmt.executeQuery().use { rs ->
                if (!rs.next()) return null
                return mapper(JdbcSqliteRow(rs))
            }
        }
    }

    override fun pragmaInt(name: String): Int =
        querySingleOrNull("PRAGMA $name") { it.getIntAt(0) ?: 0 } ?: 0

    override fun pragmaString(name: String): String =
        querySingleOrNull("PRAGMA $name") { it.getStringAt(0) ?: "" } ?: ""

    override fun <T> inTransaction(immediate: Boolean, block: () -> T): T {
        val prevAutoCommit = conn.autoCommit
        if (prevAutoCommit) {
            conn.autoCommit = false
        }
        try {
            val result = block()
            conn.commit()
            return result
        } catch (t: Throwable) {
            try {
                conn.rollback()
            } catch (_: Throwable) {
            }
            throw t
        } finally {
            if (prevAutoCommit) {
                try {
                    conn.autoCommit = true
                } catch (_: Throwable) {
                }
            }
        }
    }

    override fun close() {
        conn.close()
    }

    private fun bindArgs(stmt: PreparedStatement, args: List<Any?>) {
        for ((idx, arg) in args.withIndex()) {
            val pos = idx + 1
            when (arg) {
                null -> stmt.setNull(pos, Types.NULL)
                is String -> stmt.setString(pos, arg)
                is Int -> stmt.setInt(pos, arg)
                is Long -> stmt.setLong(pos, arg)
                is Double -> stmt.setDouble(pos, arg)
                is Float -> stmt.setFloat(pos, arg)
                is Boolean -> stmt.setInt(pos, if (arg) 1 else 0)
                else -> stmt.setObject(pos, arg)
            }
        }
    }
}

private class JdbcSqliteRow(private val rs: java.sql.ResultSet) : SqliteRow {
    override fun getString(column: String): String? = rs.getString(column)
    override fun getLong(column: String): Long? {
        val v = rs.getLong(column)
        return if (rs.wasNull()) null else v
    }
    override fun getInt(column: String): Int? {
        val v = rs.getInt(column)
        return if (rs.wasNull()) null else v
    }
    override fun getDouble(column: String): Double? {
        val v = rs.getDouble(column)
        return if (rs.wasNull()) null else v
    }
    override fun getStringAt(index: Int): String? = rs.getString(index + 1)
    override fun getLongAt(index: Int): Long? {
        val v = rs.getLong(index + 1)
        return if (rs.wasNull()) null else v
    }
    override fun getIntAt(index: Int): Int? {
        val v = rs.getInt(index + 1)
        return if (rs.wasNull()) null else v
    }
}
