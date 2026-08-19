package com.rui.astockstrategy.v6

import android.content.Context
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
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
import kotlin.math.abs

private const val EXEC_URL = "https://raw.githubusercontent.com/cskjin940509-ops/cskjin/main/astock_execution/latest.json"

private data class ExecStock(
    val code: String,
    val name: String,
    val sector: String?,
    val source: String?,
    val entryScore: Double?,
    val entryAction: String,
    val entryReason: String?,
    val holdingAction: String?,
    val holdingReason: String?,
    val price: Double?,
    val changePct: Double?,
    val dayHigh: Double?,
    val dayLow: Double?,
    val dayRangePct: Double?,
    val rangePositionPct: Double?,
    val vwap: Double?,
    val entryZoneLow: Double?,
    val entryZoneHigh: Double?,
    val riskPct: Double?,
    val protectiveStop: Double?,
    val target1R: Double?,
    val target2R: Double?,
    val mainFlowPct: Double?,
    val yunaiLargeNetInflow: Double?,
    val firstActionableAt: String?,
    val firstActionablePrice: Double?,
    val mfePct: Double?,
    val maePct: Double?,
    val bestObservedTime: String?,
    val metricPrecision: String?,
)

private data class ExecSnapshot(
    val date: String,
    val generatedAt: String,
    val phase: String,
    val refreshMin: Int,
    val stocks: List<ExecStock>,
)

private data class LocalPosition(val price: Double, val date: String, val time: String)

@Composable
fun ExecutionPanel() {
    var snapshot by remember { mutableStateOf<ExecSnapshot?>(null) }
    var quotes by remember { mutableStateOf<Map<String, Quote>>(emptyMap()) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        while (true) {
            try {
                val s = fetchExecutionSnapshot()
                snapshot = s
                if (s != null && s.stocks.isNotEmpty()) {
                    quotes = DataApi.fetchQuotes(s.stocks.map { symbol(it.code) })
                }
                error = null
            } catch (e: Exception) {
                error = e.javaClass.simpleName
            }
            delay(30_000)
        }
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xFFF8FAFF))
    ) {
        Column(Modifier.padding(13.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row {
                Column(Modifier.weight(1f)) {
                    Text("实盘执行辅助", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                    Text("后台5分钟规则信号 · 手机行情约30秒刷新", fontSize = 9.sp, color = Color(0xFF6D7480))
                }
                val s = snapshot
                Text(s?.phase ?: "等待数据", fontSize = 10.sp, fontWeight = FontWeight.SemiBold, color = Color(0xFF3567B7))
            }

            val s = snapshot
            if (s == null) {
                Text(if (error == null) "正在读取交易辅助数据" else "交易辅助暂未同步", fontSize = 11.sp, color = Color(0xFF6D7480))
            } else {
                Text("信号时间 ${shortTime(s.generatedAt)} · ${s.date}", fontSize = 9.sp, color = Color(0xFF6D7480))
                Text("只把昨日正式池和当日尾盘核心池作为交易候选；信号会失效，不能视为保证成交或保证收益。", fontSize = 9.sp, color = Color(0xFF6D7480))
                s.stocks.take(8).forEach { st ->
                    ExecutionStockCard(st, quotes[symbol(st.code)])
                }
                if (s.stocks.isEmpty()) Text("当前没有进入执行监控的股票", fontSize = 11.sp, color = Color(0xFF6D7480))
            }
        }
    }
}

@Composable
private fun ExecutionStockCard(st: ExecStock, q: Quote?) {
    val context = LocalContext.current
    val prefs = remember { context.getSharedPreferences("astock_local_positions", Context.MODE_PRIVATE) }
    var pos by remember(st.code) { mutableStateOf(loadPosition(prefs, st.code)) }

    val live = q?.price ?: st.price
    val change = q?.change ?: st.changePct
    val high = q?.high ?: st.dayHigh
    val low = q?.low ?: st.dayLow
    val today = LocalDate.now(CnZone).toString()
    val sellable = pos != null && pos!!.date < today
    val pnlPct = if (pos != null && live != null && pos!!.price > 0) (live / pos!!.price - 1.0) * 100.0 else null

    val actionColor = when (st.entryAction) {
        "介入候选" -> Color(0xFFB23A2A)
        "等待回踩", "等待企稳", "观察确认" -> Color(0xFFB67800)
        else -> Color(0xFF5F6874)
    }

    Surface(color = Color.White, shape = RoundedCornerShape(14.dp)) {
        Column(Modifier.fillMaxWidth().padding(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row {
                Column(Modifier.weight(1f)) {
                    Text("${st.name}  ${st.code}", fontWeight = FontWeight.Bold, fontSize = 13.sp)
                    Text("${st.sector ?: "未分类"} · ${sourceZh(st.source)}", fontSize = 9.sp, color = Color(0xFF6D7480))
                }
                Column(horizontalAlignment = androidx.compose.ui.Alignment.End) {
                    Text(live?.let { String.format("%.2f", it) } ?: "—", fontWeight = FontWeight.Bold)
                    Text(change?.let { String.format("%+.2f%%", it) } ?: "—", fontSize = 10.sp, color = if ((change ?: 0.0) >= 0) Color(0xFFD54432) else Color(0xFF16855B))
                }
            }

            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("最高 ${fmt(high)}", fontSize = 9.sp, color = Color(0xFF6D7480))
                Text("最低 ${fmt(low)}", fontSize = 9.sp, color = Color(0xFF6D7480))
                Text("日内区间 ${fmtPct(st.dayRangePct)}", fontSize = 9.sp, color = Color(0xFF6D7480))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("区间位置 ${fmtPct(st.rangePositionPct)}", fontSize = 9.sp, color = Color(0xFF6D7480))
                Text("分时均价 ${fmt(st.vwap)}", fontSize = 9.sp, color = Color(0xFF6D7480))
                Text("资金占比 ${fmtPct(st.mainFlowPct)}", fontSize = 9.sp, color = Color(0xFF6D7480))
            }

            Surface(color = Color(0xFFF1F4FA), shape = RoundedCornerShape(9.dp)) {
                Column(Modifier.fillMaxWidth().padding(7.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text("介入判断：${st.entryAction}", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = actionColor)
                    st.entryReason?.let { Text(it, fontSize = 8.sp, color = Color(0xFF5F6874)) }
                    Text("观察介入区 ${zone(st.entryZoneLow, st.entryZoneHigh)} · 规则评分 ${st.entryScore?.let { String.format("%.0f", it) } ?: "—"}", fontSize = 9.sp)
                    Text("模型保护位 ${fmt(st.protectiveStop)} · 1R ${fmt(st.target1R)} · 2R ${fmt(st.target2R)}", fontSize = 9.sp)
                }
            }

            if (st.firstActionableAt != null) {
                Text("首次介入信号 ${shortTime(st.firstActionableAt)} @ ${fmt(st.firstActionablePrice)}", fontSize = 9.sp, color = Color(0xFF3567B7))
                Text("信号后最大浮盈 ${signedPct(st.mfePct)} · 最大回撤 ${signedPct(st.maePct)}${st.bestObservedTime?.let { " · 最佳观察时点 ${shortTime(it)}" } ?: ""}", fontSize = 9.sp, color = Color(0xFF6D7480))
                Text("口径：${st.metricPrecision ?: "等待后续样本"}；日内最低到最高不是可实现收益。", fontSize = 8.sp, color = Color(0xFF8A9098))
            }

            if (pos == null) {
                Button(
                    onClick = {
                        if (live != null && live > 0) {
                            val now = java.time.LocalTime.now(CnZone).toString().take(8)
                            val p = LocalPosition(live, today, now)
                            savePosition(prefs, st.code, p)
                            pos = p
                        }
                    },
                    enabled = live != null && live > 0,
                    contentPadding = PaddingValues(horizontal = 10.dp, vertical = 2.dp),
                    modifier = Modifier.height(32.dp)
                ) { Text("记录我已买入", fontSize = 9.sp) }
            } else {
                Surface(color = Color(0xFFFFF7E7), shape = RoundedCornerShape(9.dp)) {
                    Column(Modifier.fillMaxWidth().padding(7.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text("我的记录成本 ${fmt(pos!!.price)} · ${pos!!.date} ${pos!!.time}", fontSize = 9.sp, fontWeight = FontWeight.Bold)
                        Text("当前浮动收益 ${signedPct(pnlPct)}", fontSize = 10.sp, color = if ((pnlPct ?: 0.0) >= 0) Color(0xFFD54432) else Color(0xFF16855B))
                        Text(
                            if (!sellable) "今日新仓：按普通A股T+1约束，今天不把离场提示当作可执行卖出。"
                            else "持仓判断：${st.holdingAction ?: "持有观察"} · ${st.holdingReason ?: "未触发保护条件"}",
                            fontSize = 9.sp,
                            color = Color(0xFF5F6874)
                        )
                        TextButton(
                            onClick = { clearPosition(prefs, st.code); pos = null },
                            contentPadding = PaddingValues(0.dp),
                            modifier = Modifier.height(28.dp)
                        ) { Text("清除持仓记录", fontSize = 9.sp) }
                    }
                }
            }
        }
    }
}

private suspend fun fetchExecutionSnapshot(): ExecSnapshot? = withContext(Dispatchers.IO) {
    val c = URL("$EXEC_URL?t=${System.currentTimeMillis()}").openConnection() as HttpURLConnection
    c.connectTimeout = 8000
    c.readTimeout = 8000
    c.setRequestProperty("User-Agent", "Mozilla/5.0 AStockStrategy-Execution/2.2")
    c.setRequestProperty("Cache-Control", "no-cache")
    try {
        if (c.responseCode !in 200..299) return@withContext null
        val root = JSONObject(c.inputStream.bufferedReader().use { it.readText() })
        val stocksObj = root.optJSONObject("stocks") ?: JSONObject()
        val ranking = root.optJSONArray("ranking")
        val codes = mutableListOf<String>()
        if (ranking != null) for (i in 0 until ranking.length()) ranking.optString(i).takeIf { it.isNotBlank() }?.let(codes::add)
        if (codes.isEmpty()) stocksObj.keys().forEachRemaining(codes::add)
        val rows = codes.mapNotNull { code ->
            val x = stocksObj.optJSONObject(code) ?: return@mapNotNull null
            ExecStock(
                code = code,
                name = x.optString("name", code),
                sector = x.optString("sector").takeIf { it.isNotBlank() },
                source = x.optString("source").takeIf { it.isNotBlank() },
                entryScore = n(x, "entryScore"),
                entryAction = x.optString("entryAction", "观察"),
                entryReason = x.optString("entryReason").takeIf { it.isNotBlank() },
                holdingAction = x.optString("holdingAction").takeIf { it.isNotBlank() },
                holdingReason = x.optString("holdingReason").takeIf { it.isNotBlank() },
                price = n(x, "price"), changePct = n(x, "changePct"), dayHigh = n(x, "dayHigh"), dayLow = n(x, "dayLow"),
                dayRangePct = n(x, "dayRangePct"), rangePositionPct = n(x, "rangePositionPct"), vwap = n(x, "vwap"),
                entryZoneLow = n(x, "entryZoneLow"), entryZoneHigh = n(x, "entryZoneHigh"), riskPct = n(x, "riskPct"),
                protectiveStop = n(x, "protectiveStop"), target1R = n(x, "target1R"), target2R = n(x, "target2R"),
                mainFlowPct = n(x, "mainFlowPct"), yunaiLargeNetInflow = n(x, "yunaiLargeNetInflow"),
                firstActionableAt = x.optString("firstActionableAt").takeIf { it.isNotBlank() }, firstActionablePrice = n(x, "firstActionablePrice"),
                mfePct = n(x, "maxFavorablePctAfterSignal"), maePct = n(x, "maxAdversePctAfterSignal"),
                bestObservedTime = x.optString("bestObservedTimeAfterSignal").takeIf { it.isNotBlank() },
                metricPrecision = x.optString("postSignalMetricPrecision").takeIf { it.isNotBlank() },
            )
        }
        ExecSnapshot(root.optString("date"), root.optString("generatedAt"), root.optString("phase", "交易辅助"), root.optInt("refreshIntervalMin", 5), rows)
    } finally { c.disconnect() }
}

private fun n(o: JSONObject, key: String): Double? {
    val v = o.opt(key)
    return when (v) { null, JSONObject.NULL -> null; is Number -> v.toDouble(); else -> v.toString().toDoubleOrNull() }
}

private fun loadPosition(prefs: android.content.SharedPreferences, code: String): LocalPosition? {
    val p = prefs.getFloat("${code}_price", Float.NaN)
    val d = prefs.getString("${code}_date", null)
    val t = prefs.getString("${code}_time", null)
    return if (!p.isNaN() && d != null && t != null) LocalPosition(p.toDouble(), d, t) else null
}

private fun savePosition(prefs: android.content.SharedPreferences, code: String, p: LocalPosition) {
    prefs.edit().putFloat("${code}_price", p.price.toFloat()).putString("${code}_date", p.date).putString("${code}_time", p.time).apply()
}

private fun clearPosition(prefs: android.content.SharedPreferences, code: String) {
    prefs.edit().remove("${code}_price").remove("${code}_date").remove("${code}_time").apply()
}

private fun sourceZh(v: String?) = when (v) { "TailCore" -> "当日尾盘核心"; "Official" -> "昨日正式池"; else -> v ?: "策略池" }
private fun fmt(v: Double?) = v?.let { String.format("%.2f", it) } ?: "—"
private fun fmtPct(v: Double?) = v?.let { String.format("%.2f%%", it) } ?: "—"
private fun signedPct(v: Double?) = v?.let { String.format("%+.2f%%", it) } ?: "—"
private fun zone(a: Double?, b: Double?) = if (a != null && b != null) "${fmt(a)}–${fmt(b)}" else "等待数据"
private fun shortTime(v: String): String {
    val s = v.substringAfter('T', v).substringAfterLast(' ')
    return if (s.length >= 8) s.take(8) else s.takeLast(8)
}
