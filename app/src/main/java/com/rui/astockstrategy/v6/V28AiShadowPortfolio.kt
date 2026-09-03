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
import java.time.DayOfWeek
import java.time.Duration
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.ZonedDateTime

private val AiBg28 = Color(0xFFF5F7FB)
private val AiMuted28 = Color(0xFF747B8D)
private val AiBlue28 = Color(0xFF3557D4)
private val AiUp28 = Color(0xFFD84343)
private val AiDown28 = Color(0xFF15966A)
private val AiAmber28 = Color(0xFFAE6A00)

private const val AI_PORTFOLIO_PATH_28 = "astock_ai_portfolio/latest.json"
private const val AI_LEDGER_PATH_28 = "astock_ai_portfolio/ledger.json"
private const val AI_AUTOMATION_PATH_28 = "astock_ai_portfolio/automation.json"

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

private suspend fun fetchAiShadow28(): JSONObject =
    JSONObject(BackendClient.fetchText(AI_PORTFOLIO_PATH_28))

private suspend fun fetchAiLedger28(): JSONArray =
    JSONArray(BackendClient.fetchText(AI_LEDGER_PATH_28))

private suspend fun fetchAiAutomation28(): JSONObject =
    JSONObject(BackendClient.fetchText(AI_AUTOMATION_PATH_28))

private fun displayTime28(value: String?): String =
    value?.replace("T", " ")?.take(19)?.ifBlank { "—" } ?: "—"

private fun automationHealthy28(o: JSONObject?): Boolean {
    if (o == null || !o.optBoolean("enabled") || o.optString("status") == "ERROR") return false
    val now = ZonedDateTime.now(ZoneId.of("Asia/Shanghai"))
    val tradingDay = now.dayOfWeek !in setOf(DayOfWeek.SATURDAY, DayOfWeek.SUNDAY)
    val tradingTime = (now.toLocalTime() >= java.time.LocalTime.of(9, 30) && now.toLocalTime() <= java.time.LocalTime.of(11, 30)) ||
        (now.toLocalTime() >= java.time.LocalTime.of(13, 0) && now.toLocalTime() <= java.time.LocalTime.of(15, 0))
    if (!tradingDay || !tradingTime) return true
    val last = runCatching { OffsetDateTime.parse(o.optString("lastRunAt")) }.getOrNull() ?: return false
    return Duration.between(last, now.toOffsetDateTime()).toMinutes() in 0..20
}

private data class AiPosition28(
    val code: String, val name: String, val sector: String, val qty: Int,
    val entryPrice: Double?, val avgCost: Double?, val currentPrice: Double?,
    val currentWeightPct: Double?, val floatingPnl: Double?, val floatingReturnPct: Double?,
    val entryTimestamp: String, val reason: String, val action: String, val invalidation: String
)
private data class AiDecision28(
    val id: String, val time: String, val side: String, val code: String, val name: String, val qty: Int,
    val price: Double?, val weight: Double?, val realizedPnl: Double?, val realizedReturn: Double?, val reason: String
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
            id = x.optString("decisionId").ifBlank { "${x.optString("timestamp")}-${x.optString("code")}-${x.optString("side")}" },
            time = x.optString("timestamp"),
            side = x.optString("sideZh").ifBlank { if (x.optString("side") == "BUY") "买入" else "卖出" },
            code = x.optString("code"),
            name = x.optString("name").ifBlank { x.optString("code") },
            qty = x.optInt("qty"),
            price = n28(x, "price"),
            weight = n28(x, "targetWeightPct"),
            realizedPnl = n28(x, "realizedPnl"),
            realizedReturn = n28(x, "realizedReturnPct"),
            reason = x.optString("reasonZh")
        )
    }
}

@Composable
fun AiShadowPortfolioScreen28() {
    var data by remember { mutableStateOf<JSONObject?>(null) }
    var ledger by remember { mutableStateOf<JSONArray?>(null) }
    var automation by remember { mutableStateOf<JSONObject?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var ledgerError by remember { mutableStateOf<String?>(null) }
    var automationError by remember { mutableStateOf<String?>(null) }
    var ledgerFilter by remember { mutableStateOf("全部") }
    var refreshGeneration by remember { mutableIntStateOf(0) }
    var refreshing by remember { mutableStateOf(false) }

    LaunchedEffect(refreshGeneration) {
        while (true) {
            refreshing = true
            runCatching { fetchAiShadow28() }
                .onSuccess { data = it; error = null }
                .onFailure { error = "影子组合数据暂未同步：${it.message ?: it.javaClass.simpleName}" }
            runCatching { fetchAiLedger28() }
                .onSuccess { ledger = it; ledgerError = null }
                .onFailure { ledgerError = "完整成交账本暂未同步：${it.message ?: it.javaClass.simpleName}" }
            runCatching { fetchAiAutomation28() }
                .onSuccess { automation = it; automationError = null }
                .onFailure { automationError = "后台自动运行状态暂未同步：${it.message ?: it.javaClass.simpleName}" }
            refreshing = false
            delay(30000)
        }
    }

    val d = data
    val summary = d?.optJSONObject("summary")
    val pos = positions28(d?.optJSONArray("positions"))
    val today = decisions28(d?.optJSONArray("todayDecisions")).asReversed()
    val allDecisions = decisions28(ledger).asReversed()
    val visibleDecisions = allDecisions.filter {
        ledgerFilter == "全部" || it.side == ledgerFilter
    }
    val daily = d?.optJSONArray("dailyPerformance")
    val rules = d?.optJSONObject("rulesZh")
    val capital = n28(summary, "capitalCapacity") ?: n28(summary, "initialCapital")

    LazyColumn(
        modifier = Modifier.fillMaxSize().background(AiBg28),
        contentPadding = PaddingValues(14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item {
            Card(shape = RoundedCornerShape(18.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
                Column(Modifier.fillMaxWidth().padding(15.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("后台自动影子组合", fontWeight = FontWeight.Bold, fontSize = 18.sp)
                            Text("${money28(capital)}模拟容量 · 关闭APK仍由云端运行", color = AiMuted28, fontSize = 10.sp)
                        }
                        OutlinedButton(onClick = { refreshGeneration++ }, enabled = !refreshing, contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp)) {
                            Text(if (refreshing) "刷新中" else "立即刷新", fontSize = 10.sp)
                        }
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

        item { AiAutomationCard28(automation, automationError) }

        item { AiBenchmarkCard28(d) }

        item { AiTitle28("当前模拟持仓") }
        if (pos.isEmpty()) item { AiEmpty28("当前没有达到观察准入的股票，影子账户保持现金。") }
        else items(pos, key = { it.code }) { p -> AiPositionCard28(p) }

        item { AiTitle28("今日影子模拟动作") }
        if (today.isEmpty()) item {
            AiEmpty28(automation?.optString("statusZh")?.takeIf { it.isNotBlank() }
                ?: "今天尚未产生买入或卖出动作；请结合后台运行状态区分无信号与任务异常。")
        }
        else items(today, key = { "today-${it.id}" }) { x -> AiDecisionCard28(x) }

        item { AiTitle28("完整成交账本（${allDecisions.size}笔）") }
        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                listOf("全部", "买入", "卖出").forEach { value ->
                    FilterChip(
                        selected = ledgerFilter == value,
                        onClick = { ledgerFilter = value },
                        label = { Text(value) },
                        modifier = Modifier.weight(1f)
                    )
                }
            }
        }
        if (ledgerError != null && allDecisions.isEmpty()) {
            item { AiEmpty28(ledgerError!!) }
        } else if (visibleDecisions.isEmpty()) {
            item { AiEmpty28("当前筛选条件下没有成交记录。") }
        } else {
            items(visibleDecisions, key = { "ledger-${it.id}" }) { x -> AiDecisionCard28(x) }
        }

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

        item { AiTitle28("本机手动试算（可选）") }
        item { PersonalAiPanel33() }
    }
}

@Composable
private fun AiAutomationCard28(o: JSONObject?, fetchError: String?) {
    val healthy = automationHealthy28(o)
    val incident = o?.optJSONObject("knownIncident")
    Card(shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.fillMaxWidth().padding(13.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("后台自动运行状态", fontWeight = FontWeight.Bold, fontSize = 14.sp)
                    Text("策略计算和模拟买卖均在云端完成，打开软件只读取结果", color = AiMuted28, fontSize = 9.sp)
                }
                Surface(color = if (healthy) Color(0xFFE8F6F0) else Color(0xFFFFECEC), shape = RoundedCornerShape(20.dp)) {
                    Text(if (healthy) "运行正常" else "需要检查", color = if (healthy) AiDown28 else AiUp28, fontWeight = FontWeight.Bold, fontSize = 9.sp, modifier = Modifier.padding(horizontal = 9.dp, vertical = 5.dp))
                }
            }
            AiAutoRow28("最近运行", displayTime28(o?.optString("lastRunAt")))
            AiAutoRow28("最近成交", displayTime28(o?.optString("lastTradeAt")))
            AiAutoRow28("本轮结果", o?.optString("statusZh")?.ifBlank { "等待后台首次运行" } ?: "等待后台首次运行")
            AiAutoRow28("运行方式", o?.optString("scheduleZh")?.ifBlank { "等待后台配置" } ?: "等待后台配置")
            AiAutoRow28("真实券商", if (o?.optBoolean("brokerConnected") == true) "已连接" else "未连接（仅模拟）")
            if (!fetchError.isNullOrBlank()) Text(fetchError, color = AiAmber28, fontSize = 9.sp)
            if (incident != null) {
                Surface(color = Color(0xFFFFF4E2), shape = RoundedCornerShape(10.dp)) {
                    Column(Modifier.fillMaxWidth().padding(9.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                        Text("历史运行空档已披露", color = AiAmber28, fontWeight = FontWeight.Bold, fontSize = 9.sp)
                        Text("${displayTime28(incident.optString("from"))} 至 ${displayTime28(incident.optString("to"))}", fontSize = 8.sp)
                        Text(incident.optString("causeZh"), color = AiMuted28, fontSize = 8.sp)
                        Text("该区间未补造买卖记录。", color = AiMuted28, fontSize = 8.sp)
                    }
                }
            }
        }
    }
}

@Composable
private fun AiAutoRow28(label: String, value: String) {
    Row(Modifier.fillMaxWidth()) {
        Text(label, color = AiMuted28, fontSize = 9.sp, modifier = Modifier.width(66.dp))
        Text(value, fontSize = 9.sp, modifier = Modifier.weight(1f))
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
            x.realizedPnl?.let { Text("本次实现盈亏 ${money28(it)}", color = pnlColor28(it), fontWeight = FontWeight.Bold, fontSize = 10.sp) }
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
