from pathlib import Path
import re

# This patch runs AFTER the existing v2.4 trade-journal patches.
root = Path('app/src/main/java/com/rui/astockstrategy/v6')
ui = root / 'V25RadarTracking.kt'
ui.write_text(r'''package com.rui.astockstrategy.v6

import androidx.compose.foundation.background
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
import kotlin.math.abs

private val V25Muted = Color(0xFF747B8D)
private val V25Red = Color(0xFFD84343)
private val V25Green = Color(0xFF15966A)
private val V25Amber = Color(0xFFAE6A00)
private val V25Blue = Color(0xFF3557D4)
private const val RADAR_URL = "https://raw.githubusercontent.com/cskjin940509-ops/cskjin/main/astock_radar/latest.json"

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
                    Text("从开盘滚动识别 Emerging → Confirming，不等涨完才筛", color = V25Muted, fontSize = 9.sp)
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
                        Row(Modifier.fillMaxWidth()) {
                            Column(Modifier.weight(1f)) {
                                Text("${s.name} ${s.code}", fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
                                Text("${s.sector} · ${s.action} · 追高${chaseZh25(s.chase)}", color = V25Muted, fontSize = 8.sp)
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
                Mini25("MFE", fractionPct25(returnField25(perf, "MFE")))
                Mini25("MAE", fractionPct25(returnField25(perf, "MAE")))
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
            Text("固定成员组合NAV", fontWeight = FontWeight.Bold, fontSize = 9.sp)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Mini25("今日NAV", fractionPct25(num25(p, "dailyReturn")))
                Mini25("累计NAV", fractionPct25(num25(p, "strategyNavReturn")))
                Mini25("平均个股", fractionPct25(num25(p, "averageCumReturn")))
                Mini25("中位个股", fractionPct25(num25(p, "medianCumReturn")))
                Mini25("最大回撤", fractionPct25(num25(p, "maxDrawdown")))
            }
            Text("当前胜率 ${fractionPct25(num25(p, "winRateCurrent"))} · 数据覆盖 ${fractionPct25(num25(p, "coverage"))}", color = V25Muted, fontSize = 8.sp)
            Text("累计NAV是组合绩效；平均个股累计仅作诊断，成员退出当前池也不会从历史记录删除。", color = V25Muted, fontSize = 8.sp)
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
    val o = JSONObject(http25(RADAR_URL))
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

private fun http25(url: String): String {
    val c = URL(url).openConnection() as HttpURLConnection
    c.connectTimeout = 8000
    c.readTimeout = 8000
    c.setRequestProperty("User-Agent", "Mozilla/5.0 AStockStrategy/2.5")
    c.setRequestProperty("Cache-Control", "no-cache")
    try {
        c.connect()
        if (c.responseCode !in 200..299) error("HTTP ${c.responseCode}")
        return c.inputStream.bufferedReader().use { it.readText() }
    } finally { c.disconnect() }
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
''', encoding='utf-8')

p = root / 'V6Activity.kt'
s = p.read_text(encoding='utf-8')

# 1) Put the all-day radar directly on Today. This avoids adding yet another bottom
# navigation item to an app that already has Today/Market/Mainline/Pools/Trades/History.
if 'EarlyRadarSummary()' not in s:
    pat = re.compile(r'(item\s*\{\s*StatusCard\(now,\s*quoteOkAt,\s*boardOkAt,\s*s\)\s*\})')
    s, n = pat.subn(r'\1\n        item { EarlyRadarSummary() }', s, count=1)
    if n != 1:
        raise SystemExit('cannot insert EarlyRadarSummary into TodayScreen')

# 2) Historical stock cards keep the old 1/5/10/20/60 strip, then add current and
# every-day path. Scope the replacement to HistoryStockRow only.
start = s.find('fun HistoryStockRow(')
if start < 0:
    raise SystemExit('HistoryStockRow missing')
end = s.find('\n@Composable', start + 10)
if end < 0:
    end = len(s)
seg = s[start:end]
if 'DailyTrackingStrip25(perf)' not in seg:
    if 'TrackingStrip(perf)' not in seg:
        raise SystemExit('HistoryStockRow TrackingStrip anchor missing')
    seg = seg.replace('TrackingStrip(perf)', 'TrackingStrip(perf)\n            DailyTrackingStrip25(perf)', 1)
    s = s[:start] + seg + s[end:]

# 3) Existing pool/sector performance cards gain NAV only when the backend supplied
# strategyNavReturn, so sector cards are unaffected.
start = s.find('fun PerformanceCard(')
if start < 0:
    raise SystemExit('PerformanceCard missing')
end = s.find('\n@Composable', start + 10)
if end < 0:
    end = len(s)
seg = s[start:end]
if 'PoolNavStrip25(p)' not in seg:
    if 'else TrackingStrip(p)' in seg:
        seg = seg.replace('else TrackingStrip(p)', 'else { TrackingStrip(p); PoolNavStrip25(p) }', 1)
    elif 'TrackingStrip(p)' in seg:
        seg = seg.replace('TrackingStrip(p)', 'TrackingStrip(p)\n        PoolNavStrip25(p)', 1)
    else:
        raise SystemExit('PerformanceCard TrackingStrip anchor missing')
    s = s[:start] + seg + s[end:]

p.write_text(s, encoding='utf-8')

# 4) Version bump after v2.4 finisher.
g = Path('app/build.gradle.kts')
gs = g.read_text(encoding='utf-8')
gs = gs.replace('versionCode = 26', 'versionCode = 27')
gs = gs.replace('versionName = "2.4.0"', 'versionName = "2.5.0"')
if 'versionName = "2.5.0"' not in gs:
    raise SystemExit('v2.5 version bump failed')
g.write_text(gs, encoding='utf-8')

assert 'EarlyRadarSummary()' in p.read_text(encoding='utf-8')
assert 'DailyTrackingStrip25(perf)' in p.read_text(encoding='utf-8')
assert 'PoolNavStrip25(p)' in p.read_text(encoding='utf-8')
print('v2.5 early radar + daily cohort tracking UI integrated')