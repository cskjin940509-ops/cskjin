package com.rui.astockstrategy.v6

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
    val risk: String,
    val amount: Double?,
    val turnover: Double?,
    val mainNetFlow: Double?,
    val reason: String?,
    val yunaiVerified: Boolean?,
    val yunaiPrice: Double?,
    val yunaiLargeNetInflow: Double?,
    val yunaiTotalNetInflow: Double?
)

data class TailSectorDetail(
    val boardCode: String,
    val name: String,
    val type: String,
    val score: Double?,
    val status: String,
    val changePct: Double?,
    val amount: Double?,
    val mainNetFlow: Double?,
    val mainFlowPct: Double?,
    val breadthPct: Double?,
    val rs20: Double?,
    val rs60: Double?,
    val mta: String?,
    val confidence: String?,
    val reason: String?
)

data class TailDecision(
    val date: String,
    val status: String,
    val phase: String?,
    val isFinal: Boolean,
    val scheduledSlot: String?,
    val refreshIntervalMin: Int,
    val capturedAt: String,
    val boardSource: String,
    val confidence: String,
    val confirmedMainlines: List<String>,
    val candidateMainlines: List<String>,
    val confirmedSectorDetails: List<TailSectorDetail>,
    val candidateSectorDetails: List<TailSectorDetail>,
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
            delay(30_000)
        }
    }

    val today = LocalDate.now(TailZone).toString()
    val now = LocalTime.now(TailZone)
    val current = tail?.takeIf { it.date == today }

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("14:30–15:00 尾盘实时池", fontWeight = FontWeight.Bold, fontSize = 17.sp)
                Text(
                    if (current?.isFinal == true) "15:00收盘锁定 · 与盘后正式池分开留档"
                    else "每5分钟重算主线与股票池 · 15:00收盘锁定",
                    fontSize = 10.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            Surface(
                color = if (current != null && !current.noTrade) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceVariant,
                shape = RoundedCornerShape(20.dp)
            ) {
                Text(
                    when {
                        current?.isFinal == true && current.noTrade -> "最终无信号"
                        current?.isFinal == true -> "最终已锁定"
                        current != null && current.noTrade -> "滚动无信号"
                        current != null -> "滚动中"
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
                        if (now.isBefore(LocalTime.of(14, 30))) "今天14:30开始生成尾盘主线与股票池，之后每5分钟更新一次。"
                        else "今日尾盘实时池尚未同步；定时任务可能有数分钟启动延迟。",
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
                Key(if (current.isFinal) "锁定时间" else "最近更新", "${current.date} ${tailTime(current.capturedAt)}")
                Key("阶段", current.phase ?: if (current.isFinal) "收盘锁定" else "尾盘滚动")
                Key("下一刷新", nextTailRefresh(current))
                Key("板块来源", current.boardSource)
                Key("置信度", current.confidence)
                Key("确认主线", current.confirmedMainlines.joinToString(" / ").ifBlank { "无" })
                if (current.confirmedMainlines.isEmpty() && current.candidateMainlines.isNotEmpty()) {
                    Key("候选观察", current.candidateMainlines.joinToString(" / "))
                }
                Text(tailTimeline(current), fontSize = 9.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }

        val tailSectors = if (current.confirmedSectorDetails.isNotEmpty()) current.confirmedSectorDetails else current.candidateSectorDetails
        if (tailSectors.isNotEmpty()) {
            Text(
                if (current.confirmedSectorDetails.isNotEmpty()) "尾盘确认主线详情" else "尾盘候选板块详情",
                fontWeight = FontWeight.Bold,
                fontSize = 14.sp
            )
            tailSectors.take(6).forEach { sector -> TailSectorDetailRow(sector, current.date) }
        }

        if (current.noTrade) {
            Notice(
                if (current.isFinal) "15:00最终锁定时没有同时满足“确认主线 + 基础强度 + 主力资金确认”的核心股票，今日尾盘最终池为空。"
                else "本轮没有同时满足“确认主线 + 基础强度 + 主力资金确认”的核心股票；下一5分钟会重新扫描，不强行给买入名单。"
            )
        } else {
            val core = current.pools["TailCore"].orEmpty()
            Text(if (current.isFinal) "尾盘最终核心池" else "尾盘实时核心池", fontWeight = FontWeight.Bold, fontSize = 14.sp)
            Text("基础强度与主力资金同时确认；每轮按当时数据重新排序。", fontSize = 9.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            core.take(8).forEach { code ->
                current.stocks[code]?.let { TailStockRow(it, current.date) }
            }
        }

        Notice(
            if (current.isFinal) "这是15:00后第一次成功计算并锁定的尾盘最终池，后续不会用盘后数据或未来表现改写。收盘正式股票池仍会独立计算。"
            else "当前是尾盘滚动池，不是最终结果。14:30后每5分钟重新计算一次，15:00后第一次成功结果会切换为尾盘最终池并锁定。"
        )
    }
}

@Composable
private fun TailStockRow(s: TailStock, date: String) {
    Card(Modifier.fillMaxWidth().clickable { DetailNav.openTailStock(s, date) }, shape = RoundedCornerShape(14.dp)) {
        Column(Modifier.fillMaxWidth().padding(11.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Row(verticalAlignment = Alignment.Top) {
                Column(Modifier.weight(1f)) {
                    Text(s.name.ifBlank { s.code }, fontWeight = FontWeight.Bold)
                    Text("${s.code} · ${s.sector} · 点开详情", fontSize = 9.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(s.price?.let { String.format("%.2f", it) } ?: "—", fontWeight = FontWeight.Bold)
                    Text(s.changePct?.let { String.format("%+.2f%%", it) } ?: "—", fontSize = 10.sp)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                MiniMetric("尾盘分", s.tailScore?.let { String.format("%.1f", it) } ?: "—", Modifier.weight(1f))
                MiniMetric("主力占比", s.mainFlowPct?.let { String.format("%+.1f%%", it) } ?: "—", Modifier.weight(1f))
                MiniMetric("20日相对强弱", s.rs20?.let { String.format("%+.1f%%", it) } ?: "—", Modifier.weight(1f))
            }
            Text("${s.pools.joinToString(" · ") { tailPoolLabel(it) }} · ${s.mta ?: "趋势待同步"} · ${s.risk}", fontSize = 9.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text("云AI量化 ${if (s.yunaiVerified == true) "行情已核对" else "核对未确认"} · 大单净流入 ${s.yunaiLargeNetInflow?.let { String.format("%+.0f", it) } ?: "未同步"}", fontSize = 8.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun TailSectorDetailRow(x: TailSectorDetail, date: String) {
    val breadth = x.breadthPct?.coerceIn(0.0, 100.0)
    val up = breadth?.toInt() ?: 0
    val down = if (breadth != null) 100 - up else 0
    val board = Board(
        code = x.boardCode,
        name = x.name,
        change = x.changePct,
        amount = x.amount,
        flow = x.mainNetFlow,
        flowPct = x.mainFlowPct,
        up = up,
        down = down,
        flat = 0,
        type = if (x.type == "概念") "concept" else "industry"
    )
    Card(
        Modifier.fillMaxWidth().clickable { DetailNav.openSector(board, date) },
        shape = RoundedCornerShape(14.dp)
    ) {
        Column(Modifier.fillMaxWidth().padding(11.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.Top) {
                Column(Modifier.weight(1f)) {
                    Text(x.name, fontWeight = FontWeight.Bold)
                    Text("${x.status} · ${x.type} · 点开查看趋势/资金/成分股", fontSize = 9.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Text(x.score?.let { String.format("%.1f", it) } ?: "—", fontWeight = FontWeight.Bold)
            }
            Text(
                "涨跌 ${x.changePct?.let { String.format("%+.2f%%", it) } ?: "—"} · " +
                    "主力占比 ${x.mainFlowPct?.let { String.format("%+.2f%%", it) } ?: "—"} · " +
                    "广度 ${x.breadthPct?.let { String.format("%.0f%%", it) } ?: "—"}",
                fontSize = 9.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Text("${x.mta ?: "趋势待同步"} · 置信度 ${x.confidence ?: "—"}", fontSize = 8.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
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

private fun tailPoolLabel(v: String): String = when (v) {
    "TB0" -> "基础强度"
    "TB3" -> "主力资金确认"
    "TailCore" -> "尾盘核心"
    else -> v
}

private fun tailTime(v: String): String = if (v.length >= 19) v.substring(11, 19) else v

private fun nextTailRefresh(d: TailDecision): String {
    if (d.isFinal) return "已锁定，不再滚动"
    val slot = d.scheduledSlot?.takeIf { it.length == 4 && it.all(Char::isDigit) }
    val total = if (slot != null) slot.substring(0, 2).toInt() * 60 + slot.substring(2, 4).toInt() else {
        val t = tailTime(d.capturedAt)
        runCatching { t.substring(0, 2).toInt() * 60 + t.substring(3, 5).toInt() }.getOrDefault(14 * 60 + 30)
    }
    val next = total + d.refreshIntervalMin.coerceAtLeast(5)
    if (next >= 15 * 60) return "15:00 收盘锁定"
    return String.format("%02d:%02d", next / 60, next % 60)
}

private fun tailTimeline(d: TailDecision): String {
    val current = d.scheduledSlot
    val slots = listOf("1430", "1435", "1440", "1445", "1450", "1455")
    val intraday = slots.joinToString("  ") { s ->
        val label = "${s.substring(0, 2)}:${s.substring(2, 4)}"
        if (!d.isFinal && s == current) "[$label]" else label
    }
    return if (d.isFinal) "$intraday  [15:00 最终]" else "$intraday  15:00 最终"
}

private suspend fun fetchTailDecision(): TailDecision = withContext(Dispatchers.IO) {
    val c = URL("$TAIL_URL?t=${System.currentTimeMillis()}").openConnection() as HttpURLConnection
    c.connectTimeout = 8_000
    c.readTimeout = 8_000
    c.setRequestProperty("User-Agent", "Mozilla/5.0 AStockStrategy/1.8")
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
    fun sectorDetails(a: org.json.JSONArray?): List<TailSectorDetail> = if (a == null) emptyList() else (0 until a.length()).mapNotNull { i ->
        val x = a.optJSONObject(i) ?: return@mapNotNull null
        val name = x.optString("name")
        if (name.isBlank()) return@mapNotNull null
        TailSectorDetail(
            boardCode = x.optString("boardCode"),
            name = name,
            type = x.optString("type", "板块"),
            score = number(x, "score"),
            status = x.optString("status", "观察"),
            changePct = number(x, "changePct"),
            amount = number(x, "amount"),
            mainNetFlow = number(x, "mainNetFlow"),
            mainFlowPct = number(x, "mainFlowPct"),
            breadthPct = number(x, "breadthPct"),
            rs20 = number(x, "RS20"),
            rs60 = number(x, "RS60"),
            mta = x.optString("MTA").takeIf { it.isNotBlank() },
            confidence = x.optString("confidence").takeIf { it.isNotBlank() },
            reason = x.optString("reason").takeIf { it.isNotBlank() }
        )
    }

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
            risk = x.optString("risk", "—"),
            amount = number(x, "amount"),
            turnover = number(x, "turnover"),
            mainNetFlow = number(x, "mainNetFlow"),
            reason = x.optString("reason").takeIf { it.isNotBlank() },
            yunaiVerified = x.optJSONObject("yunaiQuote")?.let { if (it.has("verifiedWithin1Pct")) it.optBoolean("verifiedWithin1Pct") else null },
            yunaiPrice = x.optJSONObject("yunaiQuote")?.let { number(it, "price") },
            yunaiLargeNetInflow = x.optJSONObject("yunaiCapital")?.let { number(it, "largeNetInflow") },
            yunaiTotalNetInflow = x.optJSONObject("yunaiCapital")?.let { number(it, "totalNetInflow") }
        )
    }
    return TailDecision(
        date = o.optString("date"),
        status = o.optString("status", "TailDecision"),
        phase = o.optString("phase").takeIf { it.isNotBlank() },
        isFinal = o.optBoolean("isFinal", o.optString("status") == "TailFinal"),
        scheduledSlot = o.optString("scheduledSlot").takeIf { it.isNotBlank() },
        refreshIntervalMin = o.optInt("refreshIntervalMin", 5),
        capturedAt = o.optString("capturedAt"),
        boardSource = o.optString("boardSource", "未知"),
        confidence = o.optString("confidence", "—"),
        confirmedMainlines = names(o.optJSONArray("confirmedMainlines")),
        candidateMainlines = names(o.optJSONArray("candidateMainlines")),
        confirmedSectorDetails = sectorDetails(o.optJSONArray("confirmedMainlines")),
        candidateSectorDetails = sectorDetails(o.optJSONArray("candidateMainlines")),
        pools = pools,
        stocks = stocks,
        noTrade = o.optBoolean("noTrade", true)
    )
}
