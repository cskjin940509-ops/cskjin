package com.rui.astockstrategy.v6

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.time.LocalDateTime
import java.time.ZoneId
import kotlin.math.abs

private val TradeBlue = Color(0xFF3557D4)
private val TradeRed = Color(0xFFD84343)
private val TradeGreen = Color(0xFF15966A)
private val TradeAmber = Color(0xFFAE6A00)
private val TradeMuted = Color(0xFF747B8D)
private val TradeSoft = Color(0xFFF3F5F9)

data class TradePlanRow(
    val code: String,
    val name: String,
    val sector: String?,
    val action: String,
    val setup: String,
    val score: Double?,
    val entryLow: Double?,
    val entryHigh: Double?,
    val stop: Double?,
    val tp1: Double?,
    val tp2: Double?,
    val window: String?,
    val price: Double?,
    val changePct: Double?,
    val dayHigh: Double?,
    val dayLow: Double?,
    val dayRangePct: Double?,
    val histSamples: Int,
    val histWin5D: Double?,
    val histAvg5D: Double?,
    val histMfe5D: Double?,
    val histMae5D: Double?,
    val official: Boolean,
    val tailCore: Boolean,
    val reasons: List<String>
)

data class TradePlanPayload(
    val date: String,
    val generatedAt: String,
    val phase: String,
    val officialDate: String,
    val official: List<TradePlanRow>,
    val setupCandidates: List<TradePlanRow>
)

@Composable
fun TradePlanPanel(visibleCodes: Set<String>) {
    var payload by remember { mutableStateOf<TradePlanPayload?>(null) }
    var err by remember { mutableStateOf<String?>(null) }
    var liveQuotes by remember { mutableStateOf<Map<String, Quote>>(emptyMap()) }

    LaunchedEffect(Unit) {
        while (true) {
            runCatching { fetchTradePlan() }
                .onSuccess { payload = it; err = null }
                .onFailure { err = it.javaClass.simpleName }
            delay(30000)
        }
    }
    val trackedCodes = remember(payload, visibleCodes) {
        val p = payload ?: return@remember emptyList<String>()
        (p.official.filter { visibleCodes.isEmpty() || it.code in visibleCodes }.map { it.code } + p.setupCandidates.map { it.code }).distinct()
    }
    LaunchedEffect(trackedCodes.joinToString(",")) {
        while (true) {
            if (trackedCodes.isNotEmpty()) {
                runCatching { DataApi.fetchQuotes(trackedCodes.map(::symbol)) }
                    .onSuccess { if (it.isNotEmpty()) liveQuotes = it }
            }
            delay(5000)
        }
    }

    val p = payload
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("交易计划 / 实时触发", fontSize = 17.sp, fontWeight = FontWeight.Bold)
        if (p == null) {
            Surface(color = TradeSoft, shape = RoundedCornerShape(14.dp)) {
                Text("交易计划尚未同步${err?.let { " · $it" } ?: ""}", Modifier.fillMaxWidth().padding(11.dp), color = TradeMuted, fontSize = 11.sp)
            }
            return@Column
        }
        Surface(color = Color(0xFFE9EDFF), shape = RoundedCornerShape(14.dp)) {
            Column(Modifier.fillMaxWidth().padding(11.dp)) {
                Text("${p.date} · ${phaseZh(p.phase)} · 基于 Official ${p.officialDate}", fontWeight = FontWeight.Bold, fontSize = 11.sp)
                Text("形态与价格区间同时满足才给买入候选；普通A股按T+1设计卖出条件。App每5秒看价格，后台每5分钟重算形态。", fontSize = 9.sp, color = TradeMuted)
            }
        }

        val officialRows = p.official.filter { visibleCodes.isEmpty() || it.code in visibleCodes }
        if (officialRows.isEmpty()) {
            Text("当前池暂无可计算交易形态", fontSize = 11.sp, color = TradeMuted)
        } else {
            officialRows.forEach { row -> TradePlanCard(row, liveQuotes[symbol(row.code)]) }
        }

        val anyBuy = officialRows.any { effectiveAction(it, liveQuotes[symbol(it.code)]).contains("买入") }
        if (!anyBuy && p.setupCandidates.isNotEmpty()) {
            Spacer(Modifier.height(2.dp))
            Text("Official暂无买点 · 同形态扩展候选", fontSize = 14.sp, fontWeight = FontWeight.Bold)
            Text("只从强板块扩展成分股中找历史同类形态，不把这些股票混进Official。", fontSize = 9.sp, color = TradeMuted)
            p.setupCandidates.take(8).forEach { row -> TradePlanCard(row, liveQuotes[symbol(row.code)], compact = true) }
        }
    }
}

@Composable
private fun TradePlanCard(row: TradePlanRow, q: Quote?, compact: Boolean = false) {
    val current = q?.price ?: row.price
    val action = effectiveAction(row, q)
    val actionColor = when {
        action.contains("买入") -> TradeRed
        action.contains("不建议") || action.contains("失效") -> TradeGreen
        else -> TradeAmber
    }
    val high = q?.high ?: row.dayHigh
    val low = q?.low ?: row.dayLow
    val range = if (high != null && low != null && low > 0) (high / low - 1.0) * 100.0 else row.dayRangePct
    Card(shape = RoundedCornerShape(15.dp)) {
        Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(row.name, fontWeight = FontWeight.Bold)
                    Text("${row.code} · ${row.sector ?: "—"}${if (row.tailCore) " · TailCore" else ""}", fontSize = 9.sp, color = TradeMuted)
                }
                Surface(color = actionColor.copy(alpha = 0.10f), shape = RoundedCornerShape(10.dp)) {
                    Text(action, Modifier.padding(horizontal = 8.dp, vertical = 5.dp), color = actionColor, fontWeight = FontWeight.Bold, fontSize = 10.sp)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("现价 ${fmt(current)}", fontSize = 10.sp)
                Text("涨跌 ${pct(q?.change ?: row.changePct)}", fontSize = 10.sp, color = if ((q?.change ?: row.changePct ?: 0.0) >= 0) TradeRed else TradeGreen)
                Text("形态 ${row.setup} ${row.score?.let { String.format("%.0f", it) } ?: "—"}", fontSize = 10.sp, color = TradeBlue)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("高 ${fmt(high)}", fontSize = 9.sp, color = TradeMuted)
                Text("低 ${fmt(low)}", fontSize = 9.sp, color = TradeMuted)
                Text("低→高 ${range?.let { String.format("%.2f%%", it) } ?: "—"}", fontSize = 9.sp, color = TradeMuted)
            }
            if (row.entryLow != null && row.entryHigh != null) {
                Text("买入区 ${fmt(row.entryLow)}–${fmt(row.entryHigh)} · 建议时段 ${row.window ?: "—"}", fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
                Text("失效/止损 ${fmt(row.stop)} · TP1 ${fmt(row.tp1)} · TP2 ${fmt(row.tp2)}", fontSize = 9.sp, color = TradeMuted)
            } else {
                Text("当前没有可执行入场区间", fontSize = 9.sp, color = TradeMuted)
            }
            if (row.histSamples > 0) {
                Text("历史同形态 ${row.histSamples}次 · 5D胜率 ${row.histWin5D?.let { String.format("%.0f%%", it * 100) } ?: "—"} · 平均5D ${ret(row.histAvg5D)} · MFE ${ret(row.histMfe5D)} · MAE ${ret(row.histMae5D)}", fontSize = 8.sp, color = TradeMuted)
            }
            if (!compact && row.reasons.isNotEmpty()) Text(row.reasons.joinToString(" · "), fontSize = 8.sp, color = TradeMuted, maxLines = 2)
            Text("T+1：买入当日的止损只做风险预警，不能按普通A股当天反向卖出。", fontSize = 8.sp, color = TradeAmber)
        }
    }
}

private fun effectiveAction(row: TradePlanRow, q: Quote?): String {
    val px = q?.price ?: row.price ?: return row.action
    val lo = row.entryLow; val hi = row.entryHigh
    if (row.stop != null && px <= row.stop) return "形态失效"
    if (row.tp2 != null && px >= row.tp2) return "达到TP2"
    if (row.tp1 != null && px >= row.tp1) return "达到TP1"
    if (marketOpenNow() && lo != null && hi != null && px in lo..hi && row.action == "等待触发") return "进入买入区·待确认"
    return row.action
}

private fun fetchTradePlan(): TradePlanPayload {
    val url = URL("https://raw.githubusercontent.com/cskjin940509-ops/cskjin/main/astock_trade/latest.json?t=${System.currentTimeMillis()}")
    val c = url.openConnection() as HttpURLConnection
    c.connectTimeout = 8000; c.readTimeout = 8000
    c.setRequestProperty("User-Agent", "Mozilla/5.0 AStockStrategy-TradePlan-App/1.0")
    c.setRequestProperty("Cache-Control", "no-cache")
    c.connect()
    try {
        if (c.responseCode !in 200..299) error("HTTP ${c.responseCode}")
        val o = JSONObject(c.inputStream.bufferedReader().use { it.readText() })
        return TradePlanPayload(
            date=o.optString("date"), generatedAt=o.optString("generatedAt"), phase=o.optString("phase"), officialDate=o.optString("officialDate"),
            official=parseRows(o.optJSONArray("officialPlans")), setupCandidates=parseRows(o.optJSONArray("setupCandidates"))
        )
    } finally { c.disconnect() }
}

private fun parseRows(a: JSONArray?): List<TradePlanRow> {
    if (a == null) return emptyList()
    return (0 until a.length()).mapNotNull { i ->
        val o=a.optJSONObject(i) ?: return@mapNotNull null
        val setup=o.optJSONObject("setup") ?: JSONObject(); val hist=setup.optJSONObject("historical") ?: JSONObject(); val quote=o.optJSONObject("quote") ?: JSONObject()
        val zone=o.optJSONArray("entryZone")
        TradePlanRow(
            code=o.optString("code"), name=o.optString("name"), sector=o.optString("sector").takeIf { it.isNotBlank() }, action=o.optString("action"),
            setup=setup.optString("label"), score=jnum(setup,"score"), entryLow=zone?.optDouble(0)?.takeIf { !it.isNaN() }, entryHigh=zone?.optDouble(1)?.takeIf { !it.isNaN() },
            stop=jnum(o,"stopLoss"), tp1=jnum(o,"takeProfit1"), tp2=jnum(o,"takeProfit2"), window=o.optString("preferredWindow").takeIf { it.isNotBlank() },
            price=jnum(quote,"price"), changePct=jnum(quote,"changePct"), dayHigh=jnum(quote,"high"), dayLow=jnum(quote,"low"), dayRangePct=jnum(quote,"dayLowToHighPct"),
            histSamples=hist.optInt("samples",0), histWin5D=jnum(hist,"win5D"), histAvg5D=jnum(hist,"avg5D"), histMfe5D=jnum(hist,"avgMFE5D"), histMae5D=jnum(hist,"avgMAE5D"),
            official=o.optBoolean("official",false), tailCore=o.optBoolean("tailCore",false), reasons=jsonStrings(o.optJSONArray("reasons"))
        )
    }
}

private fun jnum(o: JSONObject,key:String):Double? { val v=o.opt(key); return when(v){ is Number->v.toDouble(); else->v?.toString()?.toDoubleOrNull() } }
private fun jsonStrings(a: JSONArray?):List<String> = if(a==null) emptyList() else (0 until a.length()).mapNotNull { a.optString(it).takeIf(String::isNotBlank) }
private fun fmt(v:Double?):String = v?.let { if(abs(it)>=100) String.format("%.2f",it) else String.format("%.3f",it) } ?: "—"
private fun pct(v:Double?):String = v?.let { String.format("%+.2f%%",it) } ?: "—"
private fun ret(v:Double?):String = v?.let { String.format("%+.2f%%",it*100) } ?: "—"
private fun phaseZh(s:String)=when(s){"LIVE"->"盘中实时";"PREOPEN"->"盘前";else->"收盘/行情待刷新"}
