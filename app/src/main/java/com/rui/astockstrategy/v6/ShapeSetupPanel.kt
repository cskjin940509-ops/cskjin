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
import kotlin.math.abs

private const val SETUP_PATH = "astock_trade/latest.json"
private val SetupMuted = Color(0xFF6D7480)
private val SetupBlue = Color(0xFF3567B7)
private val SetupAmber = Color(0xFFB67800)

data class ShapeSetupRow(
    val code: String,
    val name: String,
    val sector: String?,
    val action: String,
    val pattern: String,
    val score: Double?,
    val price: Double?,
    val changePct: Double?,
    val dayHigh: Double?,
    val dayLow: Double?,
    val entryLow: Double?,
    val entryHigh: Double?,
    val stop: Double?,
    val tp1: Double?,
    val tp2: Double?,
    val window: String?,
    val samples: Int,
    val win5d: Double?,
    val avg5d: Double?,
    val mfe5d: Double?,
    val mae5d: Double?,
    val reasons: List<String>,
)

data class ShapeSetupSnapshot(
    val date: String,
    val generatedAt: String,
    val phase: String,
    val scope: String?,
    val coveragePct: Double?,
    val rows: List<ShapeSetupRow>,
)

@Composable
fun ShapeSetupPanel() {
    var snap by remember { mutableStateOf<ShapeSetupSnapshot?>(null) }
    var quotes by remember { mutableStateOf<Map<String, Quote>>(emptyMap()) }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) {
        while (true) {
            runCatching { fetchShapeSetup() }
                .onSuccess {
                    snap = it
                    error = null
                    if (it.rows.isNotEmpty()) {
                        runCatching { ResilientDataApi.fetchQuotes(it.rows.map { r -> symbol(r.code) }) }
                            .onSuccess { q -> if (q.isNotEmpty()) quotes = q }
                    }
                }
                .onFailure { error = it.javaClass.simpleName }
            delay(30_000)
        }
    }
    val s = snap

    if (s == null || s.rows.isEmpty()) {
        Card(
            Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(18.dp),
            colors = CardDefaults.cardColors(containerColor = Color(0xFFFFFBF2))
        ) {
            Column(Modifier.fillMaxWidth().padding(13.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("历史同形态候选", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                Text(
                    error?.let { "云端扫描暂未同步：$it" }
                        ?: if (s == null) "正在读取云端扫描结果…" else "本轮没有符合条件的扩展候选。",
                    color = SetupMuted,
                    fontSize = 9.sp
                )
            }
        }
        return
    }

    Card(
        Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xFFFFFBF2))
    ) {
        Column(Modifier.padding(13.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("历史同形态候选", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                    Text("Official暂无实时买点时的扩展扫描 · 不属于正式股票池", fontSize = 9.sp, color = SetupMuted)
                }
                Text(if (s.phase == "PREOPEN") "盘前" else "实时", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = SetupAmber)
            }
            Text("${s.date} · ${s.scope ?: "市场形态扫描"}${s.coveragePct?.let { " · 截面覆盖 ${String.format("%.1f%%", it)}" } ?: ""}", fontSize = 9.sp, color = SetupMuted)
            Text("这些股票只是当前形态与历史可介入形态相似；开盘后仍需实时价格、资金与入场区确认，不能把盘前形态直接当成成交指令。", fontSize = 9.sp, color = SetupMuted)
            s.rows.take(8).forEach { row -> ShapeSetupCard(row, quotes[symbol(row.code)]) }
            if (error != null) Text("最近一次刷新异常：$error", fontSize = 8.sp, color = SetupMuted)
        }
    }
}

@Composable
private fun ShapeSetupCard(row: ShapeSetupRow, q: Quote?) {
    val live = q?.price ?: row.price
    val high = q?.high ?: row.dayHigh
    val low = q?.low ?: row.dayLow
    val chg = q?.change ?: row.changePct
    Surface(color = Color.White, shape = RoundedCornerShape(13.dp)) {
        Column(Modifier.fillMaxWidth().padding(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("${row.name}  ${row.code}", fontWeight = FontWeight.Bold, fontSize = 12.sp)
                    Text("${row.pattern} · 非Official", fontSize = 9.sp, color = SetupBlue)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(fmtSetup(live), fontWeight = FontWeight.Bold)
                    Text(chg?.let { String.format("%+.2f%%", it) } ?: "—", fontSize = 9.sp, color = if ((chg ?: 0.0) >= 0) Color(0xFFD54432) else Color(0xFF16855B))
                }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("最高 ${fmtSetup(high)}", fontSize = 8.sp, color = SetupMuted)
                Text("最低 ${fmtSetup(low)}", fontSize = 8.sp, color = SetupMuted)
                Text("形态分 ${row.score?.let { String.format("%.0f", it) } ?: "—"}", fontSize = 8.sp, color = SetupMuted)
            }
            if (row.entryLow != null && row.entryHigh != null) {
                Text("观察介入区 ${fmtSetup(row.entryLow)}–${fmtSetup(row.entryHigh)} · ${row.window ?: "等待触发"}", fontSize = 9.sp, fontWeight = FontWeight.SemiBold)
                Text("保护位 ${fmtSetup(row.stop)} · 目标1 ${fmtSetup(row.tp1)} · 目标2 ${fmtSetup(row.tp2)}", fontSize = 8.sp, color = SetupMuted)
            }
            if (row.samples > 0) {
                Text("历史同形态 ${row.samples}次 · 5日胜率 ${pctHist(row.win5d)} · 平均5日 ${retHist(row.avg5d)} · MFE ${retHist(row.mfe5d)} · MAE ${retHist(row.mae5d)}", fontSize = 8.sp, color = SetupMuted)
            } else {
                Text("历史同形态样本不足，降低置信度", fontSize = 8.sp, color = SetupAmber)
            }
            Text("当前：${row.action}${if (row.reasons.isNotEmpty()) " · ${row.reasons.take(2).joinToString(" · ")}" else ""}", fontSize = 8.sp, color = SetupMuted, maxLines = 2)
        }
    }
}

private suspend fun fetchShapeSetup(): ShapeSetupSnapshot = withContext(Dispatchers.IO) {
        val o = JSONObject(BackendClient.fetchText(SETUP_PATH))
        val scan = o.optJSONObject("marketSetupScan")
        ShapeSetupSnapshot(
            date=o.optString("date"), generatedAt=o.optString("generatedAt"), phase=o.optString("phase"),
            scope=scan?.optString("scope")?.takeIf { it.isNotBlank() }, coveragePct=jnumSetup(scan,"coveragePct"),
            rows=parseSetupRows(o.optJSONArray("setupCandidates"))
        )
}

private fun parseSetupRows(a: JSONArray?): List<ShapeSetupRow> {
    if (a == null) return emptyList()
    return (0 until a.length()).mapNotNull { i ->
        val o=a.optJSONObject(i) ?: return@mapNotNull null
        val setup=o.optJSONObject("setup") ?: JSONObject(); val hist=setup.optJSONObject("historical") ?: JSONObject(); val q=o.optJSONObject("quote") ?: JSONObject(); val z=o.optJSONArray("entryZone")
        ShapeSetupRow(
            code=o.optString("code"), name=o.optString("name"), sector=o.optString("sector").takeIf { it.isNotBlank() }, action=o.optString("action"), pattern=setup.optString("label"), score=jnumSetup(setup,"score"),
            price=jnumSetup(q,"price"), changePct=jnumSetup(q,"changePct"), dayHigh=jnumSetup(q,"high"), dayLow=jnumSetup(q,"low"),
            entryLow=z?.optDouble(0)?.takeIf { !it.isNaN() }, entryHigh=z?.optDouble(1)?.takeIf { !it.isNaN() }, stop=jnumSetup(o,"stopLoss"), tp1=jnumSetup(o,"takeProfit1"), tp2=jnumSetup(o,"takeProfit2"), window=o.optString("preferredWindow").takeIf { it.isNotBlank() },
            samples=hist.optInt("samples",0), win5d=jnumSetup(hist,"win5D"), avg5d=jnumSetup(hist,"avg5D"), mfe5d=jnumSetup(hist,"avgMFE5D"), mae5d=jnumSetup(hist,"avgMAE5D"), reasons=jsonStringsSetup(o.optJSONArray("reasons"))
        )
    }
}

private fun jnumSetup(o: JSONObject?, key:String):Double? { if(o==null)return null; val v=o.opt(key); return when(v){ is Number->v.toDouble(); else->v?.toString()?.toDoubleOrNull() } }
private fun jsonStringsSetup(a:JSONArray?):List<String> = if(a==null) emptyList() else (0 until a.length()).mapNotNull { a.optString(it).takeIf(String::isNotBlank) }
private fun fmtSetup(v:Double?):String = v?.let { if(abs(it)>=100) String.format("%.2f",it) else String.format("%.3f",it) } ?: "—"
private fun pctHist(v:Double?):String = v?.let { String.format("%.0f%%",it*100) } ?: "—"
private fun retHist(v:Double?):String = v?.let { String.format("%+.2f%%",it*100) } ?: "—"
