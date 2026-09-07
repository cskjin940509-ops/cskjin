package com.rui.astockstrategy.v6

import android.content.Context
import android.content.ClipData
import android.content.ClipboardManager
import android.content.ContentValues
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.ui.platform.LocalContext

typealias AppContext = Context
typealias AppPreferences = android.content.SharedPreferences
val LocalAppContext get() = LocalContext
fun copyBackup(context: AppContext, text: String) {
    (context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager)
        .setPrimaryClip(ClipData.newPlainText("A股交易日志备份", text))
}
fun readBackup(context: AppContext): String =
    (context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager)
        .primaryClip?.getItemAt(0)?.coerceToText(context)?.toString().orEmpty()

class V6Activity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { AStockV6() }
    }
}

internal class BackendCache(context: AppContext) : SQLiteOpenHelper(
    context,
    "astock_backend_cache.db",
    null,
    1
) {
    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE backend_payload (
                path TEXT PRIMARY KEY,
                body TEXT NOT NULL,
                fetched_at INTEGER NOT NULL,
                source_url TEXT,
                server_time TEXT
            )
            """.trimIndent()
        )
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) = Unit

    fun put(path: String, body: String, fetchedAt: Long, sourceUrl: String, serverTime: String?) {
        val values = ContentValues().apply {
            put("path", path)
            put("body", body)
            put("fetched_at", fetchedAt)
            put("source_url", sourceUrl)
            put("server_time", serverTime)
        }
        writableDatabase.insertWithOnConflict(
            "backend_payload",
            null,
            values,
            SQLiteDatabase.CONFLICT_REPLACE
        )
    }

    fun get(path: String): CachedPayload? {
        readableDatabase.query(
            "backend_payload",
            arrayOf("body", "fetched_at", "server_time"),
            "path = ?",
            arrayOf(path),
            null,
            null,
            null,
            "1"
        ).use { cursor ->
            if (!cursor.moveToFirst()) return null
            return CachedPayload(
                body = cursor.getString(0),
                fetchedAt = cursor.getLong(1),
                serverTime = cursor.getString(2)
            )
        }
    }
}
