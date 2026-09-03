package com.rui.astockstrategy.v6

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.time.LocalDate
import java.time.ZoneId

/**
 * 手机直连腾讯/东方财富失败时的只读兜底。
 * 数据由 GitHub Actions 定时抓取并写入 astock_gateway/latest.json。
 * 它不替代盘中实时源，只负责避免网络/限流时整页空白。
 */
object ResilientDataApi {
    private const val GATEWAY = "https://raw.githubusercontent.com/cskjin940509-ops/cskjin/main/astock_gateway/latest.json"

    @Volatile var quoteSource: String = "腾讯行情"
        private set
    @Volatile var boardSource: String = "东方财富实时"
        private set
    @Volatile var boardIsCurrent: Boolean = false
        private set
    @Volatile var gatewayGeneratedAt: String? = null
        private set

    suspend fun fetchQuotes(symbols: List<String>): Map<String, Quote> {
        val direct = runCatching { DataApi.fetchQuotes(symbols) }.getOrNull()
        if (!direct.isNullOrEmpty()) {
            quoteSource = "腾讯行情"
            return direct
        }
        val fallback = fetchGatewayQuotes(symbols)
        quoteSource = if (fallback.isNotEmpty()) "备用市场快照" else "行情源不可用"
        return fallback
    }

    suspend fun fetchBoardsPair(): Pair<List<Board>, List<Board>> {
        // Tier 1: Eastmoney realtime.
        val directIndustry = runCatching { DataApi.fetchBoards("industry", delayed = false) }.getOrNull().orEmpty()
        val directConcept = runCatching { DataApi.fetchBoards("concept", delayed = false) }.getOrNull().orEmpty()
        if (directIndustry.isNotEmpty() || directConcept.isNotEmpty()) {
            boardSource = "东方财富实时"
            boardIsCurrent = true
            return directIndustry to directConcept
        }

        // Tier 2: Eastmoney delayed host. It is current-session data but may lag roughly 15 minutes.
        val delayedIndustry = runCatching { DataApi.fetchBoards("industry", delayed = true) }.getOrNull().orEmpty()
        val delayedConcept = runCatching { DataApi.fetchBoards("concept", delayed = true) }.getOrNull().orEmpty()
        if (delayedIndustry.isNotEmpty() || delayedConcept.isNotEmpty()) {
            boardSource = "东方财富延迟源（约15分钟）"
            boardIsCurrent = true
            return delayedIndustry to delayedConcept
        }

        // Tier 3: frozen GitHub gateway. Never label an old snapshot as realtime.
        val root = runCatching { gatewayRoot() }.getOrNull()
        if (root == null) {
            boardSource = "板块源不可用"
            boardIsCurrent = false
            return emptyList<Board>() to emptyList()
        }
        val heat = root.optJSONObject("boardHeatmap")
        val industry = parseBoards(heat?.optJSONArray("industry"), "industry")
        val concept = parseBoards(heat?.optJSONArray("concept"), "concept")
        gatewayGeneratedAt = root.optString("generatedAt").takeIf { it.isNotBlank() }
        val sourceDate = root.optJSONObject("marketSnapshot")?.optString("sourceDate")?.takeIf { it.isNotBlank() }
        val today = LocalDate.now(ZoneId.of("Asia/Shanghai")).toString()
        boardIsCurrent = sourceDate == today
        val time = gatewayGeneratedAt?.let { v -> if (v.length >= 16) v.substring(11, 16) else null }
        boardSource = if (industry.isNotEmpty() || concept.isNotEmpty()) {
            "备用快照 ${sourceDate ?: "日期未知"}${time?.let { " $it" } ?: ""}"
        } else {
            "板块源不可用"
        }
        return industry to concept
    }

    suspend fun gatewayStatus(): GatewayStatus? = withContext(Dispatchers.IO) {
        runCatching {
            val root = gatewayRoot()
            GatewayStatus(
                generatedAt = root.optString("generatedAt").takeIf { it.isNotBlank() },
                state = root.optString("state").takeIf { it.isNotBlank() } ?: "未知",
                verifiedToday = root.optBoolean("verifiedToday", false),
                providerDate = root.optString("providerDate").takeIf { it.isNotBlank() },
                errors = root.optJSONArray("errors")?.let { a ->
                    (0 until a.length()).mapNotNull { i -> a.optString(i).takeIf { it.isNotBlank() } }
                }.orEmpty()
            )
        }.getOrNull()
    }

    private suspend fun fetchGatewayQuotes(symbols: List<String>): Map<String, Quote> = withContext(Dispatchers.IO) {
        val root = gatewayRoot()
        gatewayGeneratedAt = root.optString("generatedAt").takeIf { it.isNotBlank() }
        val q = root.optJSONObject("quotes") ?: return@withContext emptyMap()
        val out = linkedMapOf<String, Quote>()
        symbols.distinct().forEach { sym ->
            val x = q.optJSONObject(sym) ?: return@forEach
            out[sym] = Quote(
                symbol = sym,
                name = x.optString("name"),
                code = x.optString("code"),
                price = n(x, "price"),
                prev = n(x, "prevClose"),
                change = n(x, "changePct"),
                high = n(x, "high"),
                low = n(x, "low"),
                amount = n(x, "amount"),
                quoteTime = x.optString("quoteTime").takeIf { it.matches(Regex("\\d{2}:\\d{2}:\\d{2}")) }
            )
        }
        out
    }

    private fun parseBoards(a: org.json.JSONArray?, type: String): List<Board> {
        if (a == null) return emptyList()
        return (0 until a.length()).mapNotNull { i ->
            val x = a.optJSONObject(i) ?: return@mapNotNull null
            val name = x.optString("name").takeIf { it.isNotBlank() } ?: return@mapNotNull null
            Board(
                code = x.optString("boardCode"),
                name = name,
                change = n(x, "changePct"),
                amount = n(x, "amount"),
                flow = n(x, "mainNetFlow"),
                flowPct = n(x, "mainFlowPct"),
                up = x.optInt("up"),
                down = x.optInt("down"),
                flat = x.optInt("flat"),
                type = type
            )
        }
    }

    private fun gatewayRoot(): JSONObject {
        val c = URL(GATEWAY + "?t=" + System.currentTimeMillis()).openConnection() as HttpURLConnection
        c.connectTimeout = 8000
        c.readTimeout = 8000
        c.setRequestProperty("User-Agent", "Mozilla/5.0 AStockStrategy/1.0")
        c.setRequestProperty("Cache-Control", "no-cache")
        c.connect()
        try {
            if (c.responseCode !in 200..299) error("HTTP ${c.responseCode}")
            return JSONObject(c.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() })
        } finally {
            c.disconnect()
        }
    }

    private fun n(o: JSONObject, k: String): Double? {
        if (!o.has(k) || o.isNull(k)) return null
        return runCatching { o.getDouble(k) }.getOrNull()
    }
}

data class GatewayStatus(
    val generatedAt: String?,
    val state: String,
    val verifiedToday: Boolean,
    val providerDate: String?,
    val errors: List<String>
)
