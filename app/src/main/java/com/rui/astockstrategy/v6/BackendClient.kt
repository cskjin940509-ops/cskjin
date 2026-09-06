package com.rui.astockstrategy.v6

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import org.json.JSONTokener
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL

data class BackendHealth(
    val lastSuccessAt: Long = 0L,
    val lastServerTime: String? = null,
    val lastPath: String? = null,
    val source: String = "尚未同步",
    val usingCache: Boolean = false,
    val lastError: String? = null
)

/**
 * The phone is a read-only client. All strategy/radar/tracking computation is
 * performed by scheduled cloud jobs and persisted before this client reads it.
 * A small SQLite last-known-good cache prevents a temporary network failure
 * from turning a previously working screen into an endless spinner.
 */
object BackendClient {
    private const val REPO_PREFIX = "cskjin940509-ops/cskjin/main/"
    private val bases = listOf(
        "https://raw.githubusercontent.com/$REPO_PREFIX",
        "https://github.com/cskjin940509-ops/cskjin/raw/refs/heads/main/"
    )
    private const val MAX_BYTES = 24 * 1024 * 1024

    @Volatile private var cache: BackendCache? = null
    private val _health = MutableStateFlow(BackendHealth())
    val health: StateFlow<BackendHealth> = _health.asStateFlow()

    fun initialize(context: AppContext) {
        if (cache == null) {
            synchronized(this) {
                if (cache == null) cache = BackendCache(context.applicationContext)
            }
        }
    }

    suspend fun fetchText(path: String): String = withContext(Dispatchers.IO) {
        require(path.isNotBlank() && !path.startsWith('/') && ".." !in path) { "非法后端路径" }
        val db = cache ?: error("BackendClient 尚未初始化")
        var lastFailure: Throwable? = null

        for (base in bases) {
            val url = base + path + "?t=" + System.currentTimeMillis()
            try {
                val body = request(url)
                validateJson(body)
                val serverTime = extractServerTime(body)
                db.put(path, body, System.currentTimeMillis(), url, serverTime)
                _health.value = BackendHealth(
                    lastSuccessAt = System.currentTimeMillis(),
                    lastServerTime = serverTime,
                    lastPath = path,
                    source = "云端预计算",
                    usingCache = false,
                    lastError = null
                )
                return@withContext body
            } catch (t: Throwable) {
                lastFailure = t
            }
        }

        val saved = db.get(path)
        if (saved != null) {
            _health.value = BackendHealth(
                lastSuccessAt = saved.fetchedAt,
                lastServerTime = saved.serverTime,
                lastPath = path,
                source = "本机数据库缓存",
                usingCache = true,
                lastError = readableError(lastFailure)
            )
            return@withContext saved.body
        }

        val message = readableError(lastFailure)
        _health.value = BackendHealth(
            lastPath = path,
            source = "后端不可用",
            usingCache = false,
            lastError = message
        )
        throw BackendUnavailableException("云端与本地缓存均不可用：$message", lastFailure)
    }

    private fun request(url: String): String {
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.instanceFollowRedirects = true
        connection.connectTimeout = 8_000
        connection.readTimeout = 12_000
        connection.setRequestProperty("User-Agent", "AStockStrategy/${AppVersion.name}")
        connection.setRequestProperty("Accept", "application/json,text/plain,*/*")
        connection.setRequestProperty("Cache-Control", "no-cache")
        return try {
            connection.connect()
            if (connection.responseCode !in 200..299) error("HTTP ${connection.responseCode}")
            val output = ByteArrayOutputStream()
            connection.inputStream.use { input ->
                val buffer = ByteArray(16 * 1024)
                var total = 0
                while (true) {
                    val read = input.read(buffer)
                    if (read < 0) break
                    total += read
                    if (total > MAX_BYTES) error("响应超过24MB安全上限")
                    output.write(buffer, 0, read)
                }
            }
            output.toString(Charsets.UTF_8.name())
        } finally {
            connection.disconnect()
        }
    }

    private fun validateJson(text: String) {
        when (JSONTokener(text).nextValue()) {
            is JSONObject, is JSONArray -> Unit
            else -> error("后端返回的不是JSON")
        }
    }

    private fun extractServerTime(text: String): String? {
        val root = runCatching { JSONObject(text) }.getOrNull() ?: return null
        return listOf("generatedAt", "updatedAt", "capturedAt", "collectedAt")
            .firstNotNullOfOrNull { key -> root.optString(key).takeIf { it.isNotBlank() } }
    }

    private fun readableError(t: Throwable?): String = when (t) {
        null -> "未知错误"
        is java.net.SocketTimeoutException -> "连接超时"
        is java.net.UnknownHostException -> "网络或域名不可达"
        else -> t.message?.take(120) ?: t.javaClass.simpleName
    }
}

class BackendUnavailableException(message: String, cause: Throwable?) : Exception(message, cause)

internal data class CachedPayload(
    val body: String,
    val fetchedAt: Long,
    val serverTime: String?
)
