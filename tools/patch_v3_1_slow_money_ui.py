from pathlib import Path

root = Path('app/src/main/java/com/rui/astockstrategy/v6')
ui = root / 'V31SlowMoney.kt'
ui.write_text(r'''package com.rui.astockstrategy.v6

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

private val S31Muted = Color(0xFF747B8D)
private val S31Blue = Color(0xFF3557D4)
private val S31Red = Color(0xFFD84343)
private val S31Green = Color(0xFF15966A)
private val S31Amber = Color(0xFFAE6A00)
private const val SLOW_RADAR_URL = "https://raw.githubusercontent.com/cskjin940509-ops/cskjin/main/astock_radar/latest.json"

data class SlowStock31(
    val code: String,
    val name: String,
    val sector: String,
    val score: Double?,
    val detail1: String,
    val detail2: String
)

data class SlowData31(
    val state: String,
    val dataDate: String,
    val b1: List<SlowStock31>,
    val b2: List<SlowStock31>,
    val b1Availability: String,
    val b2Availability: String
)

@Composable
fun SlowMoneyPanel31() {
    var data by remember { mutableStateOf<SlowData31?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) {
        while (true) {
            runCatching { fetchSlow31() }
                .onSuccess { data = it; error = null }
                .onFailure { error = it.javaClass.simpleName }
            delay(60_000)
        }
    }
    Card(shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.fillMaxWidth().padding(13.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("慢资金确认（T+1）", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                    Text("两融 + ETF一级份额 · 使用上一已发布交易日", color = S31Muted, fontSize = 9.sp)
                }
                Text(data?.dataDate?.takeIf { it.isNotBlank() } ?: "等待数据", color = if (data?.state == "ready") S31Blue else S31Amber, fontSize = 9.sp, fontWeight = FontWeight.Bold)
            }
            if (data == null) {
                Text(error?.let { "慢资金数据暂不可用：$it" } ?: "正在读取慢资金数据…", color = S31Muted, fontSize = 10.sp)
                return@Column
            }
            val d = data!!
            if (d.state != "ready") {
                Text("交易所慢资金文件尚未同步；系统不会用空值或二级市场资金替代。", color = S31Amber, fontSize = 10.sp)
            }
            SlowSection31("B1 两融资金", d.b1, d.b1Availability)
            HorizontalDivider(color = Color(0xFFF0F1F4))
            SlowSection31("B2 ETF一级资金", d.b2, d.b2Availability)
            Text("B1/B2 是日频结构因子，不是盘中实时资金。ETF金额仅以份额变化×价格作近似，评分主要使用份额变化率。", color = S31Muted, fontSize = 8.sp)
        }
    }
}

@Composable
private fun SlowSection31(title: String, rows: List<SlowStock31>, availability: String) {
    Text(title, fontWeight = FontWeight.Bold, fontSize = 11.sp)
    Text(availability.ifBlank { "数据状态未同步" }, color = S31Muted, fontSize = 8.sp)
    if (rows.isEmpty()) {
        Text("当前没有达标股票", color = S31Muted, fontSize = 9.sp)
    } else {
        rows.take(5).forEach { x ->
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("${x.name} ${x.code}", fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
                    Text("${x.sector} · ${x.detail1}", color = S31Muted, fontSize = 8.sp)
                    Text(x.detail2, color = S31Muted, fontSize = 8.sp)
                }
                Text(x.score?.let { String.format("%.0f", it) } ?: "—", fontWeight = FontWeight.Bold, fontSize = 12.sp, color = S31Blue)
            }
        }
    }
}

private suspend fun fetchSlow31(): SlowData31 = withContext(Dispatchers.IO) {
    val o = JSONObject(http31(SLOW_RADAR_URL))
    val meta = o.optJSONObject("slowMoneyFactor") ?: JSONObject()
    val pools = o.optJSONObject("pools") ?: JSONObject()
    val stocks = o.optJSONObject("stocks") ?: JSONObject()
    val avail = o.optJSONObject("factorAvailability") ?: JSONObject()
    fun rows(key: String): List<SlowStock31> {
        val a = pools.optJSONArray(key) ?: JSONArray()
        val out = mutableListOf<SlowStock31>()
        for (i in 0 until a.length()) {
            val code = a.optString(i)
            val x = stocks.optJSONObject(code) ?: continue
            if (key == "B1") {
                val md = x.optJSONObject("marginData") ?: JSONObject()
                out += SlowStock31(
                    code, x.optString("name", code), x.optString("sector", "—"), num31(x, "marginScore"),
                    "融资余额1日 ${pctFraction31(num31(md, "balanceChangePct1d"))} · 5日 ${pctFraction31(num31(md, "balanceChangePct5d"))}",
                    "两融评分 ${score31(num31(x, "marginScore"))}"
                )
            } else {
                val ed = x.optJSONObject("etfData") ?: JSONObject()
                out += SlowStock31(
                    code, x.optString("name", code), x.optString("sector", "—"), num31(x, "etfScore"),
                    "${ed.optString("theme", "行业ETF")}份额1日 ${pctFraction31(num31(ed, "shareChangePct1d"))}",
                    "5日 ${pctFraction31(num31(ed, "shareChangePct5d"))} · ETF评分 ${score31(num31(x, "etfScore"))}"
                )
            }
        }
        return out.sortedByDescending { it.score ?: -1.0 }
    }
    SlowData31(
        state = meta.optString("state", "unavailable"),
        dataDate = meta.optString("dataDate", ""),
        b1 = rows("B1"), b2 = rows("B2"),
        b1Availability = avail.optString("B1", avail.optString("两融B1", "")),
        b2Availability = avail.optString("B2", avail.optString("ETF一级申赎B2", ""))
    )
}

private fun http31(url: String): String {
    val c = URL(url).openConnection() as HttpURLConnection
    c.connectTimeout = 8000; c.readTimeout = 8000
    c.setRequestProperty("User-Agent", "Mozilla/5.0 AStockStrategy/3.1")
    c.setRequestProperty("Cache-Control", "no-cache")
    try {
        c.connect(); if (c.responseCode !in 200..299) error("HTTP ${c.responseCode}")
        return c.inputStream.bufferedReader().use { it.readText() }
    } finally { c.disconnect() }
}

private fun num31(o: JSONObject, key: String): Double? {
    if (!o.has(key) || o.isNull(key)) return null
    val v = o.opt(key)
    return when (v) { is Number -> v.toDouble(); else -> v.toString().toDoubleOrNull() }
}
private fun pctFraction31(v: Double?): String = v?.let { String.format("%+.2f%%", it * 100.0) } ?: "—"
private fun score31(v: Double?): String = v?.let { String.format("%.0f", it) } ?: "—"
''', encoding='utf-8')

p = root / 'V6Activity.kt'
s = p.read_text(encoding='utf-8')
anchor = 'item { EarlyRadarSummary() }'
if anchor not in s:
    raise SystemExit('v3.1 EarlyRadarSummary anchor missing')
if 'SlowMoneyPanel31()' not in s:
    s = s.replace(anchor, anchor + '\n        item { SlowMoneyPanel31() }', 1)
p.write_text(s, encoding='utf-8')

g = Path('app/build.gradle.kts')
gs = g.read_text(encoding='utf-8')
gs = gs.replace('versionCode = 32', 'versionCode = 33')
gs = gs.replace('versionName = "3.0.0"', 'versionName = "3.1.0"')
if 'versionName = "3.1.0"' not in gs:
    raise SystemExit('v3.1 version bump failed')
g.write_text(gs, encoding='utf-8')
print('v3.1 B1/B2 slow-money UI integrated')
