package com.rui.astockstrategy.v6

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

private const val PRE34_URL = "https://raw.githubusercontent.com/cskjin940509-ops/cskjin/main/astock_premarket/latest.json"
private val Pre34Blue = Color(0xFF3557D4)
private val Pre34Muted = Color(0xFF747B8D)
private val Pre34Red = Color(0xFFD84343)
private val Pre34Green = Color(0xFF15966A)
private val Pre34Amber = Color(0xFFAE6A00)

data class PremarketCandidate34(
    val code: String,
    val name: String,
    val sector: String,
    val tier: String,
    val score: Double?,
    val pools: String,
    val marginScore: Double?,
    val etfScore: Double?,
    val chase: String,
    val reason: String,
    val risk: String,
    val auction: String
)

data class PremarketData34(
    val state: String,
    val targetDate: String,
    val sourceDate: String,
    val factorDate: String,
    val slowFresh: Boolean,
    val generatedAt: String,
    val candidates: List<PremarketCandidate34>
)

@Composable
fun PremarketPredictionPanel34() {
    var data by remember { mutableStateOf<PremarketData34?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) {
        while (true) {
            runCatching { fetchPremarket34() }
                .onSuccess { data = it; error = null }
                .onFailure { error = it.javaClass.simpleName }
            delay(30_000)
        }
    }

    Card(shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.fillMaxWidth().padding(13.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("开盘前提前预测池", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                    Text("昨收正式池 + 最新两融/ETF慢资金 · 不读取当日9:15后的行情", color = Pre34Muted, fontSize = 9.sp)
                }
                val ready = data?.state == "ready"
                Text(
                    when {
                        data == null -> "读取中"
                        ready -> "已就绪"
                        else -> "等待慢资金"
                    },
                    color = if (ready) Pre34Green else Pre34Amber,
                    fontSize = 9.sp,
                    fontWeight = FontWeight.Bold
                )
            }

            if (data == null) {
                Text(error?.let { "预测池暂未生成：$it；现有盘中雷达和正式池不受影响。" } ?: "正在读取开盘前预测池…", color = Pre34Muted, fontSize = 9.sp)
                return@Column
            }

            val d = data!!
            Surface(color = Color(0xFFF7F8FC), shape = RoundedCornerShape(10.dp)) {
                Column(Modifier.fillMaxWidth().padding(9.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text("目标交易日 ${d.targetDate} · 来源正式池 ${d.sourceDate}", fontSize = 9.sp, fontWeight = FontWeight.SemiBold)
                    Text(
                        if (d.slowFresh) "B1两融 / B2 ETF数据日 ${d.factorDate} · 已更新到上一交易日"
                        else "B1两融 / B2 ETF尚未更新到 ${d.sourceDate}，当前不给一级优先结论",
                        color = if (d.slowFresh) Pre34Green else Pre34Amber,
                        fontSize = 8.sp
                    )
                }
            }

            if (d.candidates.isEmpty()) {
                Text("当前没有可展示的开盘前候选。", color = Pre34Muted, fontSize = 9.sp)
            } else {
                d.candidates.take(10).forEach { x ->
                    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text("${x.name} ${x.code}", fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
                                Text("${x.sector} · ${x.tier}${if (x.pools.isNotBlank()) " · ${x.pools}" else ""}", color = Pre34Muted, fontSize = 8.sp)
                            }
                            Text(x.score?.let { String.format("%.0f", it) } ?: "—", color = tierColor34(x.tier), fontSize = 12.sp, fontWeight = FontWeight.Bold)
                        }
                        val slow = buildString {
                            if (x.marginScore != null) append("两融 ${String.format("%.0f", x.marginScore)}")
                            if (x.etfScore != null) {
                                if (isNotEmpty()) append(" · ")
                                append("ETF ${String.format("%.0f", x.etfScore)}")
                            }
                            if (isNotEmpty()) append(" · ")
                            append("追高${chaseZh34(x.chase)}")
                        }
                        Text(slow, color = Pre34Muted, fontSize = 8.sp)
                        Text(x.reason, color = Pre34Muted, fontSize = 8.sp)
                        Text("风险：${x.risk}", color = Pre34Amber, fontSize = 8.sp)
                        Text("竞价确认：${x.auction}", color = Pre34Blue, fontSize = 8.sp)
                    }
                    HorizontalDivider(color = Color(0xFFF0F1F4))
                }
            }
            Text("定位：这是开盘前兼容观察池，不是买入池；9:30后仍须服从市场→板块→个股分层准入。旧评分只用于对照研究。", color = Pre34Muted, fontSize = 8.sp)
        }
    }
}

private suspend fun fetchPremarket34(): PremarketData34 = withContext(Dispatchers.IO) {
    val o = JSONObject(httpPremarket34(PRE34_URL))
    val a = o.optJSONArray("candidates") ?: JSONArray()
    val rows = (0 until a.length()).mapNotNull { i ->
        val x = a.optJSONObject(i) ?: return@mapNotNull null
        val memberships = x.optJSONArray("memberships") ?: JSONArray()
        val tags = mutableListOf<String>()
        for (j in 0 until memberships.length()) {
            when (val k = memberships.optString(j)) {
                "B0" -> tags += "B0基础"
                "B1" -> tags += "B1两融"
                "B2" -> tags += "B2 ETF"
                "B3" -> tags += "B3主力"
                "B4" -> tags += "旧B4兼容"
                "B12" -> tags += "B12两融+ETF"
                "B13" -> tags += "B13两融+主力"
                "B23" -> tags += "B23 ETF+主力"
                "B123" -> tags += "B123三类共同"
            }
        }
        PremarketCandidate34(
            code = x.optString("code"),
            name = x.optString("name", x.optString("code")),
            sector = x.optString("sector", "未分类"),
            tier = x.optString("tierZh", "观察"),
            score = numPremarket34(x, "priorityScore"),
            pools = tags.joinToString(" / "),
            marginScore = numPremarket34(x, "marginScore"),
            etfScore = numPremarket34(x, "etfScore"),
            chase = x.optString("chaseRisk", "MEDIUM"),
            reason = x.optString("reasonZh", "—"),
            risk = x.optString("riskZh", "—"),
            auction = x.optString("auctionConfirmZh", "等待集合竞价确认")
        )
    }
    PremarketData34(
        state = o.optString("state", "waiting-slow-money"),
        targetDate = o.optString("targetDate", "—"),
        sourceDate = o.optString("sourceOfficialDate", "—"),
        factorDate = o.optString("factorDataDate", "—"),
        slowFresh = o.optBoolean("slowMoneyFresh", false),
        generatedAt = o.optString("generatedAt", ""),
        candidates = rows
    )
}

private fun httpPremarket34(url: String): String {
    val c = URL(url).openConnection() as HttpURLConnection
    c.connectTimeout = 8000
    c.readTimeout = 8000
    c.setRequestProperty("User-Agent", "Mozilla/5.0 AStockStrategy/3.4")
    c.setRequestProperty("Cache-Control", "no-cache")
    try {
        c.connect()
        if (c.responseCode !in 200..299) error("HTTP ${c.responseCode}")
        return c.inputStream.bufferedReader().use { it.readText() }
    } finally { c.disconnect() }
}

private fun numPremarket34(o: JSONObject, key: String): Double? {
    if (!o.has(key) || o.isNull(key)) return null
    return when (val v = o.opt(key)) {
        is Number -> v.toDouble()
        else -> v?.toString()?.toDoubleOrNull()
    }
}

private fun chaseZh34(v: String): String = when (v.uppercase()) { "LOW" -> "低"; "MEDIUM" -> "中"; "HIGH" -> "高"; else -> "—" }
private fun tierColor34(v: String): Color = when (v) { "一级优先" -> Pre34Red; "二级观察" -> Pre34Blue; else -> Pre34Amber }
