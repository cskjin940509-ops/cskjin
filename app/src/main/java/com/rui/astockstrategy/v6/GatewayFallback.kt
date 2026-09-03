package com.rui.astockstrategy.v6

import org.json.JSONObject
import java.time.LocalDate
import java.time.ZoneId

/**
 * 云端预计算快照是首选数据源。腾讯/东方财富直连只用于补齐网关中
 * 没有的自定义股票，或云端与本地SQLite缓存都不可用时的降级显示。
 */
object ResilientDataApi {
    private const val GATEWAY_PATH = "astock_gateway/latest.json"

    @Volatile var quoteSource: String = "云端预计算"
        private set
    @Volatile var boardSource: String = "云端预计算"
        private set
    @Volatile var boardIsCurrent: Boolean = false
        private set
    @Volatile var gatewayGeneratedAt: String? = null
        private set

    suspend fun fetchQuotes(symbols: List<String>): Map<String, Quote> {
        val wanted = symbols.distinct()
        val cloud = runCatching { fetchGatewayQuotes(wanted) }.getOrElse { emptyMap() }
        val missing = wanted.filterNot(cloud::containsKey)
        if (missing.isEmpty() && cloud.isNotEmpty()) {
            quoteSource = if (BackendClient.health.value.usingCache) "手机数据库缓存" else "云端预计算快照"
            return cloud
        }

        val direct = if (missing.isNotEmpty()) {
            runCatching { DataApi.fetchQuotes(missing) }.getOrElse { emptyMap() }
        } else emptyMap()
        val merged = linkedMapOf<String, Quote>().apply {
            putAll(cloud)
            putAll(direct)
        }
        quoteSource = when {
            cloud.isNotEmpty() && direct.isNotEmpty() -> "云端快照 + 直连补齐"
            cloud.isNotEmpty() -> if (BackendClient.health.value.usingCache) "手机数据库缓存" else "云端预计算快照"
            direct.isNotEmpty() -> "第三方直连降级"
            else -> "行情源不可用"
        }
        if (merged.isEmpty()) error("云端、缓存与直连行情均不可用")
        return merged
    }

    suspend fun fetchBoardsPair(): Pair<List<Board>, List<Board>> {
        // Tier 1: scheduled cloud pipeline, then the phone's last-known-good SQLite row.
        val root = runCatching { gatewayRoot() }.getOrNull()
        if (root != null) {
            val heat = root.optJSONObject("boardHeatmap")
            val industry = parseBoards(heat?.optJSONArray("industry"), "industry")
            val concept = parseBoards(heat?.optJSONArray("concept"), "concept")
            gatewayGeneratedAt = root.optString("generatedAt").takeIf { it.isNotBlank() }
            val sourceDate = root.optJSONObject("marketSnapshot")?.optString("sourceDate")?.takeIf { it.isNotBlank() }
            val today = LocalDate.now(ZoneId.of("Asia/Shanghai")).toString()
            boardIsCurrent = sourceDate == today
            val time = gatewayGeneratedAt?.let { v -> if (v.length >= 16) v.substring(11, 16) else null }
            if (industry.isNotEmpty() || concept.isNotEmpty()) {
                boardSource = if (BackendClient.health.value.usingCache) {
                    "手机数据库缓存 ${sourceDate ?: "日期未知"}"
                } else {
                    "云端预计算 ${sourceDate ?: "日期未知"}${time?.let { " $it" } ?: ""}"
                }
                return industry to concept
            }
        }

        // Tier 2: direct feeds are display-only failover, never a strategy-computation trigger.
        val directIndustry = runCatching { DataApi.fetchBoards("industry", delayed = false) }.getOrNull().orEmpty()
        val directConcept = runCatching { DataApi.fetchBoards("concept", delayed = false) }.getOrNull().orEmpty()
        if (directIndustry.isNotEmpty() || directConcept.isNotEmpty()) {
            boardSource = "第三方直连降级"
            boardIsCurrent = true
            return directIndustry to directConcept
        }

        val delayedIndustry = runCatching { DataApi.fetchBoards("industry", delayed = true) }.getOrNull().orEmpty()
        val delayedConcept = runCatching { DataApi.fetchBoards("concept", delayed = true) }.getOrNull().orEmpty()
        if (delayedIndustry.isNotEmpty() || delayedConcept.isNotEmpty()) {
            boardSource = "第三方延迟源降级"
            boardIsCurrent = true
            return delayedIndustry to delayedConcept
        }

        boardSource = "板块源不可用"
        boardIsCurrent = false
        error("云端、缓存与板块直连源均不可用")
    }

    suspend fun gatewayStatus(): GatewayStatus? =
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

    private suspend fun fetchGatewayQuotes(symbols: List<String>): Map<String, Quote> {
        val root = gatewayRoot()
        gatewayGeneratedAt = root.optString("generatedAt").takeIf { it.isNotBlank() }
        val q = root.optJSONObject("quotes") ?: return emptyMap()
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
        return out
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

    private suspend fun gatewayRoot(): JSONObject = JSONObject(BackendClient.fetchText(GATEWAY_PATH))

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
