package com.rui.astockstrategy.v6

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId

private const val TAIL_URL = "https://raw.githubusercontent.com/cskjin940509-ops/cskjin/main/astock_tail/latest.json"
private val TailZone = ZoneId.of("Asia/Shanghai")

data class TailStock(
    val code: String,
    val name: String,
    val sector: String,
    val price: Double?,
    val changePct: Double?,
    val tailScore: Double?,
    val mainFlowPct: Double?,
    val rs20: Double?,
    val mta: String?,
    val pools: List<String>,
    val risk: String
)

data class TailDecision(
    val date: String,
    val capturedAt: String,
    val boardSource: String,
    val confidence: String,
    val confirmedMainlines: List<String>,
    val candidateMainlines: List<String>,
    val pools: Map<String, List<String>>,
    val stocks: Map<String, TailStock>,
    val noTrade: Boolean
)

@Composable
fun TailDecisionPanel() {
    var tail by remember { mutableStateOf<TailDecision?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        while (true) {
            runCatching { fetchTailDecision() }
                .onSuccess { tail = it; error = null }
                .onFailure { error = it.javaClass.simpleName }
            delay(60_000)
        }
    }

    val today = LocalDate.now(TailZone).toString()
    val now = LocalTime.now(TailZone)
    val current = tail?.takeIf { it.date == today }

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("14:30 尾盘决策池", fontWeight = FontWeight.Bold, fontSize = 17.sp)
                Text("尾盘可交易参考 · 与收盘正式池分开冻结", fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Surface(
                color = if (current != null && !current.noTrade) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceVariant,
                shape = RoundedCornerShape(20.dp)
            ) {
                Text(
                    when {
                        current != null && current.noTrade -> "无核心信号"
                        current != null -> "已冻结"
                        now.isBefore(LocalTime.of(14, 30)) -> "等待14:30"
                        else -> "生成中"
                    },
                    modifier = Modifier.padding(horizontal = 9.dp, vertical = 5.dp),
                    fontSize = 9.sp,
                    fontWeight = FontWeight.Bold
                )
            }
        }

        if (current == null) {
            Card(shape = RoundedCornerShape(16.dp)) {
                Column(Modifier.fillMaxWidth().padding(13.dp)) {
                    Text(
                        if (now.isBefore(LocalTime.of(14, 30))) "今天14:30会按当时确认主线生成尾盘板块与股票池。"
                        else "今日尾盘池尚未同步；GitHub定时任务可能有数分钟启动延迟。",
                        fontSize = 11.sp
                    )
                    tail?.let { Text("最近一次：${it.date} ${tailTime(it.capturedAt)}", fontSize = 9.sp, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                    error?.let { Text("同步状态：$it", fontSize = 9.sp, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                }
            }
            return@Column
        }

        Card(shape = RoundedCornerShape(16.dp)) {
            Column(Modifier.fillMaxWidth().padding(13.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Key("冻结时间", "${current.date} ${tailTime(current.capturedAt)}")
                Key("板块来源", current.boardSource)
                Key("置信度", current.confidence)
                Key("确认主线", current.confirmedMainlines.joinToString(" / ").ifBlank { "无" })
                if (current.confirmedMainlines.isEmpty() && current.candidateMainlines.isNotEmpty()) {
                    Key("候选观察", current.candidateMainlines.joinToString(" / "))
                }
            }
        }

        if (current.noTrade) {
            Notice("14:30 当时没有同时满足“确认主线 + 基础强度 + 主力资金确认”的核心股票，不强行给尾盘买入名单。")
        } else {
            val core = current.pools["TailCore"].orEmpty()
            Text("尾盘核心池 TailCore", fontWeight = FontWeight.Bold, fontSize = 14.sp)
            Text("TB0基础强度 ∩ TB3主力资金确认；按尾盘综合分排序。", fontSize = 9.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            core.take(8).forEach { code ->
                current.stocks[code]?.let { TailStockRow(it) }
            }
        }

        Notice("这是14:30冻结的尾盘决策依据，不是收盘结论。15:00后市场事实会重新计算，18:40生成收盘 Verified Official；14:30名单不会被收盘结果回写。")
    }
}

@Composable
private fun TailStockRow(s: TailStock) {
    Card(shape = RoundedCornerShape(14.dp)) {
        Column(Modifier.fillMaxWidth().padding(11.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Row(verticalAlignment = Alignment.Top) {
                Column(Modifier.weight(1f)) {
                    Text(s.name.ifBlank { s.code }, fontWeight = FontWeight.Bold)
                    Text("${s.code} · ${s.sector}", fontSize = 9.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(s.price?.let { String.format("%.2f", it) } ?: "—", fontWeight = FontWeight.Bold)
                    Text(s.changePct?.let { String.format("%+.2f%%", it) } ?: "—", fontSize = 10.sp)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                MiniMetric("尾盘分", s.tailScore?.let { String.format("%.1f", it) } ?: "—", Modifier.weight(1f))
                MiniMetric("主力占比", s.mainFlowPct?.let { String.format("%+.1f%%", it) } ?: "—", Modifier.weight(1f))
                MiniMetric("RS20", s.rs20?.let { String.format("%+.1f%%", it) } ?: "—", Modifier.weight(1f))
            }
            Text("${s.pools.joinToString(" · ")} · ${s.mta ?: "趋势待同步"} · ${s.risk}", fontSize = 9.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun MiniMetric(label: String, value: String, modifier: Modifier) {
    Column(modifier.background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(8.dp)).padding(6.dp)) {
        Text(label, fontSize = 8.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
    }
}

private fun tailTime(v: String): String = if (v.length >= 19) v.substring(11, 19) else v

private suspend fun fetchTailDecision(): TailDecision = withContext(Dispatchers.IO) {
    val c = URL("$TAIL_URL?t=${System.currentTimeMillis()}").openConnection() as HttpURLConnection
    c.connectTimeout = 8_000
    c.readTimeout = 8_000
    c.setRequestProperty("User-Agent", "Mozilla/5.0 AStockStrategy/1.7")
    c.setRequestProperty("Cache-Control", "no-cache")
    c.connect()
    try {
        if (c.responseCode !in 200..299) error("HTTP ${c.responseCode}")
        parseTail(JSONObject(c.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }))
    } finally {
        c.disconnect()
    }
}

private fun parseTail(o: JSONObject): TailDecision {
    fun strings(a: org.json.JSONArray?): List<String> = if (a == null) emptyList() else (0 until a.length()).mapNotNull { i -> a.optString(i).takeIf { it.isNotBlank() } }
    fun names(a: org.json.JSONArray?): List<String> = if (a == null) emptyList() else (0 until a.length()).mapNotNull { i -> a.optJSONObject(i)?.optString("name")?.takeIf { it.isNotBlank() } }
    fun number(x: JSONObject, k: String): Double? = if (!x.has(k) || x.isNull(k)) null else runCatching { x.getDouble(k) }.getOrNull()

    val poolsObj = o.optJSONObject("pools") ?: JSONObject()
    val pools = listOf("TB0", "TB3", "TailCore").associateWith { strings(poolsObj.optJSONArray(it)) }
    val stocks = linkedMapOf<String, TailStock>()
    val so = o.optJSONObject("stocks") ?: JSONObject()
    val it = so.keys()
    while (it.hasNext()) {
        val code = it.next()
        val x = so.optJSONObject(code) ?: continue
        stocks[code] = TailStock(
            code = code,
            name = x.optString("name"),
            sector = x.optString("sector"),
            price = number(x, "price"),
            changePct = number(x, "changePct"),
            tailScore = number(x, "tailScore"),
            mainFlowPct = number(x, "mainFlowPct"),
            rs20 = number(x, "RS20"),
            mta = x.optString("MTA").takeIf { it.isNotBlank() },
            pools = strings(x.optJSONArray("pools")),
            risk = x.optString("risk", "—")
        )
    }
    return TailDecision(
        date = o.optString("date"),
        capturedAt = o.optString("capturedAt"),
        boardSource = o.optString("boardSource", "未知"),
        confidence = o.optString("confidence", "—"),
        confirmedMainlines = names(o.optJSONArray("confirmedMainlines")),
        candidateMainlines = names(o.optJSONArray("candidateMainlines")),
        pools = pools,
        stocks = stocks,
        noTrade = o.optBoolean("noTrade", true)
    )
}
