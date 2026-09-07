package com.rui.astockstrategy.v6

import androidx.compose.runtime.staticCompositionLocalOf
import org.json.JSONObject
import java.awt.Toolkit
import java.awt.datatransfer.DataFlavor
import java.awt.datatransfer.StringSelection
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.security.MessageDigest
import java.util.concurrent.ConcurrentHashMap

class AppContext(val directory: Path) {
    val applicationContext get() = this
    private val preferences = ConcurrentHashMap<String, AppPreferences>()
    fun getSharedPreferences(name: String, mode: Int): AppPreferences =
        preferences.computeIfAbsent(name) { AppPreferences(directory.resolve("preferences").resolve("$name.json")) }
    companion object { const val MODE_PRIVATE = 0 }
}
val LocalAppContext = staticCompositionLocalOf<AppContext> { error("桌面存储尚未初始化") }

internal fun writeAtomic(path: Path, body: String) {
    Files.createDirectories(path.parent)
    val temp = Files.createTempFile(path.parent, "astock-", ".tmp")
    try {
        Files.writeString(temp, body)
        try {
            Files.move(temp, path, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
        } catch (_: java.nio.file.AtomicMoveNotSupportedException) {
            Files.move(temp, path, StandardCopyOption.REPLACE_EXISTING)
        }
    } finally { Files.deleteIfExists(temp) }
}

class AppPreferences(private val path: Path) {
    private fun load(): JSONObject = if (Files.exists(path)) JSONObject(Files.readString(path)) else JSONObject()
    @Synchronized fun getString(key: String, fallback: String?): String? {
        val data = load()
        return if (data.has(key) && !data.isNull(key)) data.getString(key) else fallback
    }
    @Synchronized fun getFloat(key: String, fallback: Float): Float = load().optDouble(key, fallback.toDouble()).toFloat()
    fun edit() = Editor()
    inner class Editor {
        private val changes = linkedMapOf<String, Any?>()
        fun putString(key: String, value: String?) = apply { changes[key] = value }
        fun putFloat(key: String, value: Float) = apply { changes[key] = value }
        fun remove(key: String) = apply { changes[key] = null }
        fun apply() {
            synchronized(this@AppPreferences) {
                val data = load()
                changes.forEach { (key, value) -> if (value == null) data.remove(key) else data.put(key, value) }
                writeAtomic(path, data.toString())
            }
        }
    }
}

fun copyBackup(context: AppContext, text: String) {
    Toolkit.getDefaultToolkit().systemClipboard.setContents(StringSelection(text), null)
}
fun readBackup(context: AppContext): String = runCatching {
    Toolkit.getDefaultToolkit().systemClipboard.getData(DataFlavor.stringFlavor) as? String ?: ""
}.getOrDefault("")

internal class BackendCache(context: AppContext) {
    private val directory = context.directory.resolve("cache")
    private fun file(path: String): Path = directory.resolve(
        MessageDigest.getInstance("SHA-256").digest(path.toByteArray()).joinToString("") { "%02x".format(it) } + ".json"
    )
    @Synchronized fun put(path: String, body: String, fetchedAt: Long, sourceUrl: String, serverTime: String?) {
        writeAtomic(file(path), JSONObject().put("body", body).put("fetchedAt", fetchedAt)
            .put("sourceUrl", sourceUrl).put("serverTime", serverTime).toString())
    }
    @Synchronized fun get(path: String): CachedPayload? = runCatching {
        val row = JSONObject(Files.readString(file(path)))
        CachedPayload(row.getString("body"), row.getLong("fetchedAt"),
            if (row.isNull("serverTime")) null else row.getString("serverTime"))
    }.getOrNull()
}
