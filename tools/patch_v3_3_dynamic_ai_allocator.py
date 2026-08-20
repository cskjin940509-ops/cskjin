from pathlib import Path

root = Path('app/src/main/java/com/rui/astockstrategy/v6')
ui = root / 'V33DynamicAiAllocator.kt'
ui.write_text(r'''package com.rui.astockstrategy.v6

import android.content.Context
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.floor

private const val SMART33_URL = "https://raw.githubusercontent.com/cskjin940509-ops/cskjin/main/astock_ai_portfolio/latest.json"
private val D33Blue = Color(0xFF3557D4)
private val D33Red = Color(0xFFD84343)
private val D33Green = Color(0xFF15966A)
private val D33Amber = Color(0xFFAE6A00)
private val D33Muted = Color(0xFF747B8D)

private data class Target33(
    val code: String, val name: String, val sector: String, val score: Double?,
    val targetWeight: Double, val currentWeight: Double, val gap: Double,
    val action: String, val price: Double?, val reason: String
)
private data class Decision33(
    val time: String, val side: String, val name: String, val code: String,
    val qty: Int, val price: Double?, val targetWeight: Double?, val reason: String
)

private fun n33(o: JSONObject?, key: String): Double? {
    if (o == null || !o.has(key) || o.isNull(key)) return null
    return when (val v = o.opt(key)) { is Number -> v.toDouble(); else -> v?.toString()?.toDoubleOrNull() }
}
private fun money33(v: Double?): String = v?.let {
    when {
        kotlin.math.abs(it) >= 100000000 -> String.format("¥%.2f亿", it / 100000000.0)
        kotlin.math.abs(it) >= 10000 -> String.format("¥%.2f万", it / 10000.0)
        else -> String.format("¥%.0f", it)
    }
} ?: "—"
private fun pct33(v: Double?): String = v?.let { String.format("%.2f%%", it) } ?: "—"
private fun score33(v: Double?): String = v?.let { String.format("%.1f", it) } ?: "—"
private fun targets33(a: JSONArray?): List<Target33> {
    if (a == null) return emptyList()
    return (0 until a.length()).mapNotNull { i ->
        val x = a.optJSONObject(i) ?: return@mapNotNull null
        Target33(
            x.optString("code"), x.optString("name").ifBlank { x.optString("code") },
            x.optString("sector").ifBlank { "未知" }, n33(x,"score"),
            n33(x,"targetWeightPct") ?: 0.0, n33(x,"currentWeightPct") ?: 0.0,
            n33(x,"gapPct") ?: 0.0, x.optString("actionZh").ifBlank { "持有" },
            n33(x,"referencePrice"), x.optString("reasonZh")
        )
    }
}
private fun decisions33(a: JSONArray?): List<Decision33> {
    if (a == null) return emptyList()
    return (0 until a.length()).mapNotNull { i ->
        val x = a.optJSONObject(i) ?: return@mapNotNull null
        Decision33(
            x.optString("timestamp"), x.optString("sideZh").ifBlank { if (x.optString("side") == "BUY") "买入" else "卖出" },
            x.optString("name").ifBlank { x.optString("code") }, x.optString("code"), x.optInt("qty"),
            n33(x,"price"), n33(x,"targetWeightPct"), x.optString("reasonZh")
        )
    }
}
private suspend fun fetch33(): JSONObject = withContext(Dispatchers.IO) {
    val c = URL(SMART33_URL).openConnection() as HttpURLConnection
    c.connectTimeout = 8000; c.readTimeout = 8000
    c.setRequestProperty("User-Agent", "Mozilla/5.0 AStockStrategy/3.3")
    c.setRequestProperty("Cache-Control", "no-cache")
    try {
        c.connect(); if (c.responseCode !in 200..299) error("HTTP ${c.responseCode}")
        JSONObject(c.inputStream.bufferedReader().use { it.readText() })
    } finally { c.disconnect() }
}

@Composable
fun DynamicAiPortfolioScreen33() {
    val context = LocalContext.current
    val prefs = remember { context.getSharedPreferences("smart_shadow_settings", Context.MODE_PRIVATE) }
    val saved = remember { prefs.getLong("capital_rmb", 1_000_000L).toDouble() }
    var capital by remember { mutableDoubleStateOf(saved) }
    var capitalText by remember { mutableStateOf(saved.toLong().toString()) }
    var capitalError by remember { mutableStateOf<String?>(null) }
    var data by remember { mutableStateOf<JSONObject?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        while (true) {
            runCatching { fetch33() }
                .onSuccess { data = it; error = null }
                .onFailure { error = "智能实盘数据暂未同步" }
            delay(20_000)
        }
    }

    val d = data
    val summary = d?.optJSONObject("summary")
    val target = d?.optJSONObject("targetPortfolio")
    val rows = targets33(target?.optJSONArray("members"))
    val decisions = decisions33(d?.optJSONArray("todayDecisions")).asReversed()
    val rules = d?.optJSONObject("rulesZh")
    val refCapital = n33(summary, "initialCapital") ?: n33(d, "referenceCapital") ?: 1_000_000.0
    val referenceNav = n33(summary, "totalAssets") ?: refCapital
    val scaledNav = if (refCapital > 0) capital * referenceNav / refCapital else capital

    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            Card(shape = RoundedCornerShape(18.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
                Column(Modifier.fillMaxWidth().padding(15.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("智能实盘 · 动态组合", fontWeight = FontWeight.Bold, fontSize = 18.sp)
                            Text("每轮行情重新判断买入 / 加仓 / 减仓 / 卖出", color = D33Muted, fontSize = 10.sp)
                        }
                        Text(d?.optString("updatedAt")?.substringAfter("T")?.take(5) ?: "—", color = D33Blue, fontSize = 10.sp)
                    }
                    Text(money33(scaledNav), fontWeight = FontWeight.Bold, fontSize = 27.sp)
                    Text("按我的模拟资金额度折算 · 策略收益率不因资金调整被改写", color = D33Muted, fontSize = 9.sp)
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        DMetric33("当前仓位", pct33(n33(target,"currentGrossPct") ?: n33(summary,"positionPct")), D33Blue, Modifier.weight(1f))
                        DMetric33("目标仓位", pct33(n33(target,"grossTargetPct")), D33Red, Modifier.weight(1f))
                        DMetric33("目标现金", pct33(n33(target,"targetCashPct")), D33Muted, Modifier.weight(1f))
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        DMetric33("今日收益", pct33(n33(summary,"todayReturnPct")), if ((n33(summary,"todayReturnPct") ?: 0.0) >= 0) D33Red else D33Green, Modifier.weight(1f))
                        DMetric33("累计收益", pct33(n33(summary,"cumulativeReturnPct")), if ((n33(summary,"cumulativeReturnPct") ?: 0.0) >= 0) D33Red else D33Green, Modifier.weight(1f))
                        DMetric33("持仓数", summary?.optInt("positionCount")?.toString() ?: "—", D33Blue, Modifier.weight(1f))
                    }
                }
            }
        }

        item {
            Card(shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
                Column(Modifier.fillMaxWidth().padding(13.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                    Text("模拟资金额度", fontWeight = FontWeight.Bold, fontSize = 14.sp)
                    Text("你可以随时修改。资金只改变目标金额和股数，不改变策略实时权重，也不会倒改历史收益。", color = D33Muted, fontSize = 9.sp)
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedTextField(
                            value = capitalText,
                            onValueChange = { capitalText = it.filter { ch -> ch.isDigit() || ch == '.' } },
                            label = { Text("人民币") },
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                            singleLine = true,
                            modifier = Modifier.weight(1f)
                        )
                        Button(onClick = {
                            val v = capitalText.toDoubleOrNull()
                            if (v == null || v < 10_000) {
                                capitalError = "金额至少为1万元"
                            } else {
                                val old = capital
                                capital = v
                                capitalError = null
                                val t = SimpleDateFormat("MM-dd HH:mm", Locale.CHINA).format(Date())
                                val oldLog = prefs.getString("capital_log", "").orEmpty()
                                val entry = "$t  ${old.toLong()} → ${v.toLong()}"
                                val log = (listOf(entry) + oldLog.lines().filter { it.isNotBlank() }).take(8).joinToString("\n")
                                prefs.edit().putLong("capital_rmb", v.toLong()).putString("capital_log", log).apply()
                            }
                        }) { Text("应用") }
                    }
                    capitalError?.let { Text(it, color = D33Amber, fontSize = 9.sp) }
                    Text("当前额度：${money33(capital)}", color = D33Blue, fontWeight = FontWeight.Bold, fontSize = 11.sp)
                    val log = prefs.getString("capital_log", "").orEmpty().lines().filter { it.isNotBlank() }.take(3)
                    if (log.isNotEmpty()) {
                        HorizontalDivider()
                        Text("最近资金变动", color = D33Muted, fontSize = 9.sp)
                        log.forEach { Text(it, fontSize = 9.sp) }
                    }
                }
            }
        }

        if (error != null) item { DNotice33(error!!, D33Amber) }
        item { DNotice33("后台参考账户固定100万元用于保持历史成交可审计；你的额度在本机按相同实时目标权重换算。目标权重每次盘中雷达刷新都会重新计算，当前约5分钟一次。", D33Blue) }

        item { Text("实时目标组合", fontWeight = FontWeight.Bold, fontSize = 14.sp) }
        if (rows.isEmpty()) item { DNotice33("当前没有形成有效目标组合；系统允许保持现金。", D33Muted) }
        else items(rows, key = { it.code }) { x ->
            val targetAmount = capital * x.targetWeight / 100.0
            val currentAmount = capital * x.currentWeight / 100.0
            val targetQty = x.price?.takeIf { it > 0 }?.let { floor(targetAmount / it / 100.0).toInt() * 100 }
            val currentQty = x.price?.takeIf { it > 0 }?.let { floor(currentAmount / it / 100.0).toInt() * 100 }
            val delta = if (targetQty != null && currentQty != null) targetQty - currentQty else null
            Card(shape = RoundedCornerShape(15.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
                Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("${x.name} ${x.code}", fontWeight = FontWeight.Bold, fontSize = 13.sp)
                            Text("${x.sector} · 动态分 ${score33(x.score)}", color = D33Muted, fontSize = 9.sp)
                        }
                        Text(x.action, color = when (x.action) { "买入", "加仓" -> D33Red; "卖出", "减仓" -> D33Green; else -> D33Blue }, fontWeight = FontWeight.Bold)
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        DMetric33("当前权重", pct33(x.currentWeight), D33Muted, Modifier.weight(1f))
                        DMetric33("目标权重", pct33(x.targetWeight), D33Blue, Modifier.weight(1f))
                        DMetric33("差额", pct33(x.gap), if (x.gap >= 0) D33Red else D33Green, Modifier.weight(1f))
                    }
                    Text("按当前额度：目标 ${money33(targetAmount)}${targetQty?.let { " · ${it}股" } ?: ""}", fontSize = 9.sp)
                    delta?.let {
                        val label = when { it > 0 -> "需买/加仓约 ${it}股"; it < 0 -> "需减/卖约 ${-it}股"; else -> "股数已接近目标" }
                        Text(label, color = if (it > 0) D33Red else if (it < 0) D33Green else D33Muted, fontWeight = FontWeight.Bold, fontSize = 10.sp)
                    }
                    if (x.reason.isNotBlank()) Text(x.reason, color = D33Muted, fontSize = 8.sp, maxLines = 2)
                }
            }
        }

        item { Text("今日动态交易", fontWeight = FontWeight.Bold, fontSize = 14.sp) }
        if (decisions.isEmpty()) item { DNotice33("今天尚未产生交易动作。", D33Muted) }
        else items(decisions.take(30), key = { "${it.time}-${it.code}-${it.side}-${it.qty}" }) { x ->
            Card(shape = RoundedCornerShape(14.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
                Column(Modifier.fillMaxWidth().padding(11.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Row {
                        Text(x.side, color = if (x.side == "买入" || x.side == "加仓") D33Red else D33Green, fontWeight = FontWeight.Bold, modifier = Modifier.width(44.dp))
                        Text("${x.name} ${x.code}", fontWeight = FontWeight.Bold, fontSize = 11.sp, modifier = Modifier.weight(1f))
                        Text(x.time.replace("T"," ").take(16), color = D33Muted, fontSize = 8.sp)
                    }
                    Text("${x.qty}股 · ${x.price?.let { String.format("%.2f", it) } ?: "—"}${x.targetWeight?.let { " · 目标 ${pct33(it)}" } ?: ""}", fontSize = 9.sp)
                    if (x.reason.isNotBlank()) Text(x.reason, color = D33Muted, fontSize = 8.sp, maxLines = 2)
                }
            }
        }

        item { Text("动态组合规则", fontWeight = FontWeight.Bold, fontSize = 14.sp) }
        item {
            Card(shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
                Column(Modifier.fillMaxWidth().padding(13.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                    DRule33("实时再平衡", rules?.optString("rebalance"))
                    DRule33("买入 / 加仓", rules?.optString("newEntry"))
                    DRule33("仓位", rules?.optString("position"))
                    DRule33("卖出", rules?.optString("exit"))
                    DRule33("资金", rules?.optString("capital"))
                    DRule33("审计", rules?.optString("audit"))
                    Text(d?.optString("disclaimerZh") ?: "智能实盘为模拟影子组合，不连接券商。", color = D33Muted, fontSize = 8.sp)
                }
            }
        }
    }
}

@Composable private fun DMetric33(label:String,value:String,color:Color,modifier:Modifier=Modifier){ Column(modifier){ Text(label,color=D33Muted,fontSize=8.sp);Text(value,color=color,fontWeight=FontWeight.Bold,fontSize=11.sp) } }
@Composable private fun DNotice33(text:String,color:Color){ Surface(color=Color.White,shape=RoundedCornerShape(13.dp)){ Text(text,Modifier.fillMaxWidth().padding(11.dp),color=color,fontSize=9.sp) } }
@Composable private fun DRule33(title:String,text:String?){ if(text.isNullOrBlank())return; Column{ Text(title,color=D33Blue,fontWeight=FontWeight.Bold,fontSize=9.sp);Text(text,fontSize=9.sp) } }
''', encoding='utf-8')

v6 = root / 'V6Activity.kt'
s = v6.read_text(encoding='utf-8')
old = 'Tab.AI_SHADOW -> AiShadowPortfolioScreen28()'
new = 'Tab.AI_SHADOW -> DynamicAiPortfolioScreen33()'
if old in s:
    s = s.replace(old, new, 1)
elif new not in s:
    raise SystemExit('v3.3 AI route anchor missing')
v6.write_text(s, encoding='utf-8')

g = Path('app/build.gradle.kts')
gs = g.read_text(encoding='utf-8')
gs = gs.replace('versionCode = 34', 'versionCode = 35')
gs = gs.replace('versionName = "3.2.0"', 'versionName = "3.3.0"')
if 'versionName = "3.3.0"' not in gs:
    raise SystemExit('v3.3 version bump failed')
g.write_text(gs, encoding='utf-8')

assert ui.exists()
assert 'DynamicAiPortfolioScreen33()' in v6.read_text(encoding='utf-8')
print('v3.3 dynamic AI allocator and configurable capital UI integrated')
