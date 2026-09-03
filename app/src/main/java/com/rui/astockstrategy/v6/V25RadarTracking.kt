package com.rui.astockstrategy.v6

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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

private val V25Muted = Color(0xFF747B8D)
private val V25Red = Color(0xFFD84343)
private val V25Green = Color(0xFF15966A)
private val V25Amber = Color(0xFFAE6A00)
private val V25Blue = Color(0xFF3557D4)
private const val RADAR_PATH = "astock_radar/latest.json"

data class RadarLine25(
    val name: String,
    val stage: String,
    val score: Double?,
    val accumulation: Double?,
    val change: Double?,
    val chase: String,
    val leadMin: Int?
)

data class RadarStock25(
    val code: String,
    val name: String,
    val sector: String,
    val score: Double?,
    val action: String,
    val chase: String,
    val change: Double?
)

data class Radar25(
    val status: String,
    val capturedAt: String,
    val lines: List<RadarLine25>,
    val early: List<RadarStock25>,
    val note: String
)

@Composable
fun EarlyRadarSummary() {
    var radar by remember { mutableStateOf<Radar25?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) {
        while (true) {
            runCatching { fetchRadar25() }
                .onSuccess { radar = it; error = null }
                .onFailure { error = it.javaClass.simpleName }
            delay(20_000)
        }
    }
    Card(shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.fillMaxWidth().padding(13.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("全天主线提前雷达", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                    Text("从开盘滚动识别潜在形成 → 确认中，不等涨完才筛", color = V25Muted, fontSize = 9.sp)
                }
                Text(radar?.status?.let(::radarStatusZh25) ?: "读取中", color = V25Blue, fontSize = 9.sp, fontWeight = FontWeight.Bold)
            }
            if (radar == null) {
                Text(error?.let { "雷达暂不可用：$it" } ?: "正在读取盘中雷达…", color = V25Muted, fontSize = 10.sp)
            } else {
                radar!!.lines.take(4).forEach { x ->
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(x.name, fontWeight = FontWeight.SemiBold, fontSize = 11.sp)
                            Text("${stageZh25(x.stage)} · 吸筹 ${score25(x.accumulation)} · 追高 ${chaseZh25(x.chase)}${x.leadMin?.let { " · 领先${it}分" } ?: ""}", color = V25Muted, fontSize = 8.sp)
                        }
                        Column(horizontalAlignment = Alignment.End) {
                            Text(score25(x.score), fontWeight = FontWeight.Bold, fontSize = 12.sp, color = stageColor25(x.stage))
                            Text(x.change?.let(::pct25) ?: "—", color = x.change?.let(::pnl25) ?: V25Muted, fontSize = 9.sp)
                        }
                    }
                    HorizontalDivider(color = Color(0xFFF0F1F4))
                }
                if (radar!!.early.isNotEmpty()) {
                    Text("提前候选", fontWeight = FontWeight.Bold, fontSize = 11.sp)
                    radar!!.early.take(4).forEach { s ->
                        Row(Modifier.fillMaxWidth().clickable { DetailNav.openStock(s.code, null) }) {
                            Column(Modifier.weight(1f)) {
                                Text("${s.name} ${s.code}", fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
                                Text("${s.sector} · ${s.action} · 追高风险${chaseZh25(s.chase)} · 点开查看并交易", color = V25Muted, fontSize = 8.sp)
                            }
                            Column(horizontalAlignment = Alignment.End) {
                                Text("提前分 ${score25(s.score)}", fontSize = 9.sp, fontWeight = FontWeight.Bold)
                                Text(s.change?.let(::pct25) ?: "—", color = s.change?.let(::pnl25) ?: V25Muted, fontSize = 8.sp)
                            }
                        }
                    }
                }
                Text("形成分是未校准的研究评分，不是上涨概率；高追高风险时即使主线强也不建议机械追价。", color = V25Amber, fontSize = 8.sp)
            }
        }
    }
}

@Composable
fun DailyTrackingStrip25(perf: JSONObject?) {
    if (perf == null) return
    val series = perf.optJSONArray("dailySeries") ?: return
    if (series.length() == 0) return
    Spacer(Modifier.height(7.dp))
    Surface(color = Color(0xFFF7F8FC), shape = RoundedCornerShape(10.dp)) {
        Column(Modifier.fillMaxWidth().padding(8.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text("逐日跟踪", fontWeight = FontWeight.Bold, fontSize = 9.sp)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Mini25("今日", fractionPct25(num25(perf, "dailyReturn")))
                Mini25("累计", fractionPct25(num25(perf, "cumulativeReturn")))
                Mini25("最大有利涨幅", fractionPct25(returnField25(perf, "MFE")))
                Mini25("最大不利跌幅", fractionPct25(returnField25(perf, "MAE")))
                Mini25("最大回撤", fractionPct25(num25(perf, "maxDrawdown")))
            }
            val start = (series.length() - 5).coerceAtLeast(0)
            for (i in start until series.length()) {
                val x = series.optJSONObject(i) ?: continue
                Row(Modifier.fillMaxWidth()) {
                    Text(x.optString("date").takeLast(5), Modifier.weight(1f), fontSize = 8.sp, color = V25Muted)
                    Text("当日 ${fractionPct25(num25(x, "dailyReturn"))}", Modifier.weight(1f), fontSize = 8.sp)
                    Text("累计 ${fractionPct25(num25(x, "cumulativeReturn"))}", Modifier.weight(1f), fontSize = 8.sp, color = pnl25((num25(x, "cumulativeReturn") ?: 0.0)))
                }
            }
        }
    }
}

@Composable
fun PoolNavStrip25(p: JSONObject?) {
    if (p == null || !p.has("strategyNavReturn")) return
    Spacer(Modifier.height(7.dp))
    Surface(color = Color(0xFFF7F8FC), shape = RoundedCornerShape(10.dp)) {
        Column(Modifier.fillMaxWidth().padding(8.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text("固定成员组合净值", fontWeight = FontWeight.Bold, fontSize = 9.sp)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Mini25("今日组合", fractionPct25(num25(p, "dailyReturn")))
                Mini25("累计组合", fractionPct25(num25(p, "strategyNavReturn")))
                Mini25("平均个股", fractionPct25(num25(p, "averageCumReturn")))
                Mini25("中位个股", fractionPct25(num25(p, "medianCumReturn")))
                Mini25("最大回撤", fractionPct25(num25(p, "maxDrawdown")))
            }
            Text("当前胜率 ${fractionPct25(num25(p, "winRateCurrent"))} · 数据覆盖 ${fractionPct25(num25(p, "coverage"))}", color = V25Muted, fontSize = 8.sp)
            Text("累计组合是组合绩效；平均个股累计仅作诊断，成员退出当前池也不会从历史记录删除。", color = V25Muted, fontSize = 8.sp)
        }
    }
}

@Composable
private fun Mini25(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(label, fontSize = 7.sp, color = V25Muted)
        Text(value, fontSize = 8.sp, fontWeight = FontWeight.SemiBold)
    }
}

private suspend fun fetchRadar25(): Radar25 = withContext(Dispatchers.IO) {
    val o = JSONObject(BackendClient.fetchText(RADAR_PATH))
    val linesA = o.optJSONArray("mainlines") ?: JSONArray()
    val lines = (0 until linesA.length()).mapNotNull { i ->
        val x = linesA.optJSONObject(i) ?: return@mapNotNull null
        RadarLine25(
            x.optString("name"), x.optString("stage"), num25(x, "formationScore"),
            num25(x, "accumulationScore"), num25(x, "changePct"), x.optString("chaseRisk"),
            if (x.has("leadTimeMin") && !x.isNull("leadTimeMin")) x.optInt("leadTimeMin") else null
        )
    }
    val stocksO = o.optJSONObject("stocks") ?: JSONObject()
    val pools = o.optJSONObject("pools") ?: JSONObject()
    val codes = mutableListOf<String>()
    listOf("EarlyEntry", "EarlyWatch", "Confirming", "EstablishedLowChase").forEach { k ->
        val a = pools.optJSONArray(k) ?: return@forEach
        for (i in 0 until a.length()) a.optString(i).takeIf { it.isNotBlank() }?.let(codes::add)
    }
    val early = codes.distinct().mapNotNull { c ->
        val x = stocksO.optJSONObject(c) ?: return@mapNotNull null
        RadarStock25(c, x.optString("name", c), x.optString("sector"), num25(x, "earlyEntryScore"), x.optString("actionZh", "观察"), x.optString("chaseRisk"), num25(x, "changePct"))
    }.sortedByDescending { it.score ?: 0.0 }
    Radar25(o.optString("status"), o.optString("capturedAt"), lines, early, o.optString("note"))
}

private fun num25(o: JSONObject, key: String): Double? {
    if (!o.has(key) || o.isNull(key)) return null
    val v = o.opt(key)
    return when (v) { is Number -> v.toDouble(); else -> v.toString().toDoubleOrNull() }
}

private fun returnField25(o: JSONObject, key: String): Double? {
    val v = o.opt(key)
    return when (v) {
        is Number -> v.toDouble()
        is JSONObject -> num25(v, "return")
        else -> null
    }
}

private fun score25(v: Double?): String = v?.let { String.format("%.0f", it) } ?: "—"
private fun fractionPct25(v: Double?): String = v?.let { String.format("%+.2f%%", it * 100.0) } ?: "—"
private fun pct25(v: Double): String = String.format("%+.2f%%", v)
private fun pnl25(v: Double): Color = if (v >= 0) V25Red else V25Green
private fun stageZh25(v: String): String = when (v) {
    "EMERGING" -> "潜在形成"; "CONFIRMING" -> "确认中"; "ESTABLISHED" -> "已成主线"
    "OVERHEATED" -> "过热"; "FADING" -> "衰退"; "RADAR" -> "雷达"; else -> "观察"
}
private fun chaseZh25(v: String): String = when (v) { "HIGH" -> "高"; "MEDIUM" -> "中"; "LOW" -> "低"; else -> "—" }
private fun radarStatusZh25(v: String): String = when (v) { "RadarLive" -> "盘中滚动"; "RadarFinal" -> "收盘冻结"; else -> v }
private fun stageColor25(v: String): Color = when (v) { "EMERGING", "CONFIRMING" -> V25Blue; "OVERHEATED" -> V25Amber; "FADING" -> V25Green; else -> V25Red }
