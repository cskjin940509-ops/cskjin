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
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

private val AiBg28 = Color(0xFFF5F7FB)
private val AiMuted28 = Color(0xFF747B8D)
private val AiBlue28 = Color(0xFF3557D4)
private val AiUp28 = Color(0xFFD84343)
private val AiDown28 = Color(0xFF15966A)
private val AiAmber28 = Color(0xFFAE6A00)

private const val AI_PORTFOLIO_URL_28 =
    "https://raw.githubusercontent.com/cskjin940509-ops/cskjin/main/astock_ai_portfolio/latest.json"

private fun n28(o: JSONObject?, key: String): Double? {
    if (o == null || !o.has(key) || o.isNull(key)) return null
    return when (val v = o.opt(key)) {
        is Number -> v.toDouble()
        else -> v?.toString()?.toDoubleOrNull()
    }
}
private fun pct28(v: Double?): String = v?.let { String.format("%+.2f%%", it) } ?: "—"
private fun money28(v: Double?): String = v?.let {
    when {
        kotlin.math.abs(it) >= 100000000 -> String.format("¥%.2f亿", it / 100000000.0)
        kotlin.math.abs(it) >= 10000 -> String.format("¥%.2f万", it / 10000.0)
        else -> String.format("¥%.2f", it)
    }
} ?: "—"
private fun price28(v: Double?): String = v?.let { String.format("%.2f", it) } ?: "—"
private fun pnlColor28(v: Double?): Color = if ((v ?: 0.0) >= 0) AiUp28 else AiDown28

private suspend fun fetchAiShadow28(): JSONObject = withContext(Dispatchers.IO) {
    val c = URL(AI_PORTFOLIO_URL_28).openConnection() as HttpURLConnection
    c.connectTimeout = 8000
    c.readTimeout = 8000
    c.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android 16)")
    c.setRequestProperty("Cache-Control", "no-cache")
    try {
        if (c.responseCode !in 200..299) error("HTTP ${c.responseCode}")
        JSONObject(c.inputStream.bufferedReader().use { it.readText() })
    } finally { c.disconnect() }
}

private data class AiPosition28(
    val code: String, val name: String, val sector: String, val qty: Int,
    val entryPrice: Double?, val avgCost: Double?, val currentPrice: Double?,
    val currentWeightPct: Double?, val floatingPnl: Double?, val floatingReturnPct: Double?,
    val entryTimestamp: String, val reason: String, val action: String, val invalidation: String
)
private data class AiDecision28(
    val time: String, val side: String, val code: String, val name: String, val qty: Int,
    val price: Double?, val weight: Double?, val realizedReturn: Double?, val reason: String
)

private fun positions28(a: JSONArray?): List<AiPosition28> {
    if (a == null) return emptyList()
    return (0 until a.length()).mapNotNull { i ->
        val x = a.optJSONObject(i) ?: return@mapNotNull null
        AiPosition28(
            code = x.optString("code"),
            name = x.optString("name").ifBlank { x.optString("code") },
            sector = x.optString("sector").ifBlank { "未知板块" },
            qty = x.optInt("qty"),
            entryPrice = n28(x, "entryPrice"),
            avgCost = n28(x, "avgCost"),
            currentPrice = n28(x, "currentPrice"),
            currentWeightPct = n28(x, "currentWeightPct"),
            floatingPnl = n28(x, "floatingPnl"),
            floatingReturnPct = n28(x, "floatingReturnPct"),
            entryTimestamp = x.optString("entryTimestamp"),
            reason = x.optString("buyReasonZh"),
            action = x.optString("currentActionZh"),
            invalidation = x.optString("invalidationZh")
        )
    }
}
private fun decisions28(a: JSONArray?): List<AiDecision28> {
    if (a == null) return emptyList()
    return (0 until a.length()).mapNotNull { i ->
        val x = a.optJSONObject(i) ?: return@mapNotNull null
        AiDecision28(
            time = x.optString("timestamp"),
            side = x.optString("sideZh").ifBlank { if (x.optString("side") == "BUY") "买入" else "卖出" },
            code = x.optString("code"),
            name = x.optString("name").ifBlank { x.optString("code") },
            qty = x.optInt("qty"),
            price = n28(x, "price"),
            weight = n28(x, "targetWeightPct"),
            realizedReturn = n28(x, "realizedReturnPct"),
            reason = x.optString("reasonZh")
        )
    }
}

@Composable
fun AiShadowPortfolioScreen28() {
    var data by remember { mutableStateOf<JSONObject?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        while (true) {
            runCatching { fetchAiShadow28() }
                .onSuccess { data = it; error = null }
                .onFailure { error = "影子组合数据暂未同步" }
            delay(30000)
        }
    }

    val d = data
    val summary = d?.optJSONObject("summary")
    val pos = positions28(d?.optJSONArray("positions"))
    val today = decisions28(d?.optJSONArray("todayDecisions")).asReversed()
    val daily = d?.optJSONArray("dailyPerformance")
    val rules = d?.optJSONObject("rulesZh")

    LazyColumn(
        modifier = Modifier.fillMaxSize().background(AiBg28),
        contentPadding = PaddingValues(14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item { PersonalAiPanel33() }
        item {
            Card(shape = RoundedCornerShape(18.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
                Column(Modifier.fillMaxWidth().padding(15.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("样本外影子组合", fontWeight = FontWeight.Bold, fontSize = 18.sp)
                            Text("固定100万元模拟参考 · 与个人模拟账户分开记账", color = AiMuted28, fontSize = 10.sp)
                        }
                        Text(d?.optString("updatedAt")?.substringAfter("T")?.take(5) ?: "—", color = AiBlue28, fontSize = 11.sp)
                    }
                    Spacer(Modifier.height(4.dp))
                    Text(money28(n28(summary, "totalAssets")), fontWeight = FontWeight.Bold, fontSize = 27.sp)
                    Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                        AiMetric28("今日收益", pct28(n28(summary, "todayReturnPct")), pnlColor28(n28(summary, "todayReturnPct")), Modifier.weight(1f))
                        AiMetric28("累计收益", pct28(n28(summary, "cumulativeReturnPct")), pnlColor28(n28(summary, "cumulativeReturnPct")), Modifier.weight(1f))
                        AiMetric28("最大回撤", pct28(n28(summary, "maxDrawdownPct")), AiDown28, Modifier.weight(1f))
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                        AiMetric28("持仓比例", pct28(n28(summary, "positionPct")), AiBlue28, Modifier.weight(1f))
                        AiMetric28("现金比例", pct28(n28(summary, "cashPct")), AiMuted28, Modifier.weight(1f))
                        AiMetric28("胜率", pct28(n28(summary, "winRatePct")), AiAmber28, Modifier.weight(1f))
                    }
                    HorizontalDivider()
                    Row {
                        Text("已实现盈亏", color = AiMuted28, fontSize = 10.sp, modifier = Modifier.weight(1f))
                        Text(money28(n28(summary, "realizedPnl")), color = pnlColor28(n28(summary, "realizedPnl")), fontWeight = FontWeight.Bold, fontSize = 11.sp)
                    }
                    Row {
                        Text("持仓浮动盈亏", color = AiMuted28, fontSize = 10.sp, modifier = Modifier.weight(1f))
                        Text(money28(n28(summary, "floatingPnl")), color = pnlColor28(n28(summary, "floatingPnl")), fontWeight = FontWeight.Bold, fontSize = 11.sp)
                    }
                }
            }
        }

        if (error != null) {
            item {
                Surface(color = Color(0xFFFFF4E2), shape = RoundedCornerShape(12.dp)) {
                    Text(error!!, Modifier.fillMaxWidth().padding(10.dp), color = AiAmber28, fontSize = 10.sp)
                }
            }
        }

        item { AiBenchmarkCard28(d) }

        item { AiTitle28("当前模拟持仓") }
        if (pos.isEmpty()) item { AiEmpty28("当前没有达到观察准入的股票，影子账户保持现金。") }
        else items(pos, key = { it.code }) { p -> AiPositionCard28(p) }

        item { AiTitle28("今日影子模拟动作") }
        if (today.isEmpty()) item { AiEmpty28("今天尚未产生买入或卖出动作。没有合格机会时允许不交易。") }
        else items(today, key = { "${it.time}-${it.code}-${it.side}" }) { x -> AiDecisionCard28(x) }

        item { AiTitle28("组合逐日收益") }
        if (daily == null || daily.length() == 0) {
            item { AiEmpty28("逐日净值将在影子组合运行后持续积累。") }
        } else {
            item {
                Card(shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
                    Column(Modifier.fillMaxWidth().padding(13.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                        val start = maxOf(0, daily.length() - 12)
                        for (i in daily.length() - 1 downTo start) {
                            val x = daily.optJSONObject(i) ?: continue
                            Row {
                                Text(x.optString("date"), Modifier.weight(1f), fontSize = 10.sp)
                                Text("当日 ${pct28(n28(x, "dailyReturnPct"))}", Modifier.width(100.dp), color = pnlColor28(n28(x, "dailyReturnPct")), fontSize = 10.sp)
                                Text("累计 ${pct28(n28(x, "cumulativeReturnPct"))}", color = pnlColor28(n28(x, "cumulativeReturnPct")), fontSize = 10.sp)
                            }
                        }
                    }
                }
            }
        }

        item { AiTitle28("影子组合规则") }
        item {
            Card(shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
                Column(Modifier.fillMaxWidth().padding(13.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    AiRule28("买入", rules?.optString("newEntry"))
                    AiRule28("仓位", rules?.optString("position"))
                    AiRule28("卖出", rules?.optString("exit"))
                    AiRule28("审计", rules?.optString("audit"))
                    Text("仅用于策略验证，不连接券商，也不会发送真实订单。", color = AiMuted28, fontSize = 9.sp)
                }
            }
        }
    }
}

@Composable
private fun AiMetric28(label: String, value: String, color: Color, modifier: Modifier = Modifier) {
    Column(modifier) {
        Text(label, color = AiMuted28, fontSize = 9.sp)
        Text(value, color = color, fontWeight = FontWeight.Bold, fontSize = 12.sp)
    }
}
@Composable private fun AiTitle28(s: String) { Text(s, fontWeight = FontWeight.Bold, fontSize = 14.sp) }
@Composable
private fun AiEmpty28(s: String) {
    Surface(color = Color.White, shape = RoundedCornerShape(14.dp)) {
        Text(s, Modifier.fillMaxWidth().padding(13.dp), color = AiMuted28, fontSize = 10.sp)
    }
}
@Composable
private fun AiPositionCard28(p: AiPosition28) {
    Card(shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.fillMaxWidth().padding(13.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("${p.name}  ${p.code}", fontWeight = FontWeight.Bold, fontSize = 14.sp)
                    Text("${p.sector} · ${p.qty}股", color = AiMuted28, fontSize = 9.sp)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(pct28(p.floatingReturnPct), color = pnlColor28(p.floatingReturnPct), fontWeight = FontWeight.Bold, fontSize = 16.sp)
                    Text(money28(p.floatingPnl), color = pnlColor28(p.floatingPnl), fontSize = 9.sp)
                }
            }
            Row {
                AiMetric28("买入价", price28(p.entryPrice ?: p.avgCost), AiMuted28, Modifier.weight(1f))
                AiMetric28("现价", price28(p.currentPrice), pnlColor28(p.floatingReturnPct), Modifier.weight(1f))
                AiMetric28("当前仓位", pct28(p.currentWeightPct), AiBlue28, Modifier.weight(1f))
            }
            Text("买入时点 ${p.entryTimestamp.replace("T", " ").take(16)}", color = AiMuted28, fontSize = 9.sp)
            Surface(color = Color(0xFFEFF3FF), shape = RoundedCornerShape(9.dp)) {
                Column(Modifier.fillMaxWidth().padding(8.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text("当前判断：${p.action.ifBlank { "继续观察" }}", color = AiBlue28, fontWeight = FontWeight.Bold, fontSize = 9.sp)
                    if (p.reason.isNotBlank()) Text("买入理由：${p.reason}", fontSize = 9.sp)
                    if (p.invalidation.isNotBlank()) Text("失效条件：${p.invalidation}", color = AiMuted28, fontSize = 8.sp)
                }
            }
        }
    }
}
@Composable
private fun AiDecisionCard28(x: AiDecision28) {
    val buy = x.side == "买入"
    Card(shape = RoundedCornerShape(14.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(x.side, color = if (buy) AiUp28 else AiDown28, fontWeight = FontWeight.Bold, modifier = Modifier.width(40.dp))
                Text("${x.name} ${x.code}", fontWeight = FontWeight.Bold, fontSize = 12.sp, modifier = Modifier.weight(1f))
                Text(x.time.replace("T", " ").take(16), color = AiMuted28, fontSize = 8.sp)
            }
            Text("${x.qty}股 · 成交模拟价 ${price28(x.price)}${x.weight?.let { " · 目标仓位 ${pct28(it)}" } ?: ""}", fontSize = 9.sp)
            x.realizedReturn?.let { Text("本次实现收益 ${pct28(it)}", color = pnlColor28(it), fontWeight = FontWeight.Bold, fontSize = 10.sp) }
            if (x.reason.isNotBlank()) Text("理由：${x.reason}", color = AiMuted28, fontSize = 9.sp)
        }
    }
}
@Composable
private fun AiRule28(title: String, text: String?) {
    if (text.isNullOrBlank()) return
    Column {
        Text(title, color = AiBlue28, fontWeight = FontWeight.Bold, fontSize = 9.sp)
        Text(text, fontSize = 9.sp)
    }
}


@Composable
private fun AiBenchmarkCard28(d: JSONObject?) {
    val b = d?.optJSONObject("benchmarkComparison")
    if (b == null) {
        Card(shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
            Column(Modifier.fillMaxWidth().padding(13.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("同期基准比较", fontWeight = FontWeight.Bold, fontSize = 14.sp)
                Text("基准将在下一次与主线雷达同步刷新时开始记录，不回填历史价格。", color = AiMuted28, fontSize = 9.sp)
            }
        }
        return
    }
    val started = b.optString("startedAt").replace("T", " ").take(16)
    val port = n28(b, "portfolioReturnPct")
    val indexes = b.optJSONArray("indexes")
    val pool = b.optJSONObject("candidatePool")
    Card(shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.fillMaxWidth().padding(13.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("同期基准比较", fontWeight = FontWeight.Bold, fontSize = 14.sp)
                    Text("起始 $started · 不事后倒填", color = AiMuted28, fontSize = 8.sp)
                }
                Text("智能组合 ${pct28(port)}", color = pnlColor28(port), fontWeight = FontWeight.Bold, fontSize = 11.sp)
            }
            HorizontalDivider()
            if (indexes != null) {
                for (i in 0 until indexes.length()) {
                    val x = indexes.optJSONObject(i) ?: continue
                    val r = n28(x, "returnPct")
                    val a = n28(x, "alphaPct")
                    Row {
                        Text(x.optString("name"), Modifier.weight(1f), fontSize = 10.sp)
                        Text("同期 ${pct28(r)}", Modifier.width(90.dp), color = pnlColor28(r), fontSize = 9.sp)
                        Text("超额 ${pct28(a)}", color = pnlColor28(a), fontWeight = FontWeight.Bold, fontSize = 9.sp)
                    }
                }
            }
            if (pool != null) {
                val r = n28(pool, "returnPct")
                val a = n28(pool, "alphaPct")
                Row {
                    Text("原始候选池等权（${pool.optInt("memberCount")}只）", Modifier.weight(1f), fontSize = 10.sp)
                    Text("同期 ${pct28(r)}", Modifier.width(90.dp), color = pnlColor28(r), fontSize = 9.sp)
                    Text("超额 ${pct28(a)}", color = pnlColor28(a), fontWeight = FontWeight.Bold, fontSize = 9.sp)
                }
                val definition = pool.optString("definitionZh")
                if (definition.isNotBlank()) Text(definition, color = AiMuted28, fontSize = 8.sp)
            }
            val note = b.optString("noteZh")
            if (note.isNotBlank()) Text(note, color = AiMuted28, fontSize = 8.sp)
        }
    }
}
