package org.rootwise.android.core.db

import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import java.nio.file.Path

/**
 * Android runtime implementation of [SqliteDriver] backed directly by `android.database.sqlite.SQLiteDatabase`
 * with zero third-party dependencies.
 */
object AndroidSqliteDriver : SqliteDriver {
    override fun openReadWrite(path: Path): SqliteConnection {
        val db = SQLiteDatabase.openDatabase(
            path.toFile().absolutePath,
            null,
            SQLiteDatabase.OPEN_READWRITE or SQLiteDatabase.CREATE_IF_NECESSARY
        )
        return AndroidSqliteConnection(db)
    }

    override fun openReadOnly(path: Path): SqliteConnection {
        val db = SQLiteDatabase.openDatabase(
            path.toFile().absolutePath,
            null,
            SQLiteDatabase.OPEN_READONLY
        )
        return AndroidSqliteConnection(db)
    }
}

private class AndroidSqliteConnection(private val db: SQLiteDatabase) : SqliteConnection {
    override fun execute(sql: String, args: List<Any?>) {
        val trimmed = sql.trimStart()
        if (trimmed.startsWith("PRAGMA", ignoreCase = true)) {
            db.rawQuery(sql, null).use { cursor ->
                cursor.moveToFirst()
            }
            return
        }
        if (args.isEmpty()) {
            db.execSQL(sql)
        } else {
            val bindArray = Array<Any?>(args.size) { i ->
                when (val v = args[i]) {
                    is Boolean -> if (v) 1 else 0
                    else -> v
                }
            }
            db.execSQL(sql, bindArray)
        }
    }

    override fun executeScript(sqlScript: String) {
        val statements = sqlScript
            .split(';')
            .map { it.trim() }
            .filter { it.isNotEmpty() }
        for (stmt in statements) {
            execute(stmt)
        }
    }

    override fun <T> query(sql: String, args: List<Any?>, mapper: (SqliteRow) -> T): List<T> {
        val selectionArgs = args.map { it?.toString() }.toTypedArray()
        db.rawQuery(sql, if (args.isEmpty()) null else selectionArgs).use { cursor ->
            val results = mutableListOf<T>()
            val row = AndroidCursorRow(cursor)
            while (cursor.moveToNext()) {
                results.add(mapper(row))
            }
            return results
        }
    }

    override fun <T> querySingleOrNull(sql: String, args: List<Any?>, mapper: (SqliteRow) -> T): T? {
        val selectionArgs = args.map { it?.toString() }.toTypedArray()
        db.rawQuery(sql, if (args.isEmpty()) null else selectionArgs).use { cursor ->
            if (!cursor.moveToFirst()) return null
            return mapper(AndroidCursorRow(cursor))
        }
    }

    override fun pragmaInt(name: String): Int =
        querySingleOrNull("PRAGMA $name") { it.getIntAt(0) ?: 0 } ?: 0

    override fun pragmaString(name: String): String =
        querySingleOrNull("PRAGMA $name") { it.getStringAt(0) ?: "" } ?: ""

    override fun <T> inTransaction(immediate: Boolean, block: () -> T): T {
        if (immediate) {
            db.beginTransactionNonExclusive()
        } else {
            db.beginTransaction()
        }
        try {
            val result = block()
            db.setTransactionSuccessful()
            return result
        } finally {
            db.endTransaction()
        }
    }

    override fun close() {
        db.close()
    }
}

private class AndroidCursorRow(private val cursor: Cursor) : SqliteRow {
    override fun getString(column: String): String? {
        val idx = cursor.getColumnIndexOrThrow(column)
        return if (cursor.isNull(idx)) null else cursor.getString(idx)
    }

    override fun getLong(column: String): Long? {
        val idx = cursor.getColumnIndexOrThrow(column)
        return if (cursor.isNull(idx)) null else cursor.getLong(idx)
    }

    override fun getInt(column: String): Int? {
        val idx = cursor.getColumnIndexOrThrow(column)
        return if (cursor.isNull(idx)) null else cursor.getInt(idx)
    }

    override fun getDouble(column: String): Double? {
        val idx = cursor.getColumnIndexOrThrow(column)
        return if (cursor.isNull(idx)) null else cursor.getDouble(idx)
    }

    override fun getStringAt(index: Int): String? =
        if (cursor.isNull(index)) null else cursor.getString(index)

    override fun getLongAt(index: Int): Long? =
        if (cursor.isNull(index)) null else cursor.getLong(index)

    override fun getIntAt(index: Int): Int? =
        if (cursor.isNull(index)) null else cursor.getInt(index)
}
