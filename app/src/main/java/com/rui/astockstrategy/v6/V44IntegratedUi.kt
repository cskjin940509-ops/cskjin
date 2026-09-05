package com.rui.astockstrategy.v6

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import org.json.JSONObject
import java.time.ZoneId
import kotlin.math.abs

private const val DASH_PORTFOLIO_44 = "astock_ai_portfolio/latest.json"
private const val DASH_AUTOMATION_44 = "astock_ai_portfolio/automation.json"

private val DashBg44 = Color(0xFFF4F6FA)
private val DashInk44 = Color(0xFF172033)
private val DashMuted44 = Color(0xFF6E778A)
private val DashBlue44 = Color(0xFF3157D5)
private val DashNavy44 = Color(0xFF18284F)
private val DashRed44 = Color(0xFFD64545)
private val DashGreen44 = Color(0xFF128163)
private val DashAmber44 = Color(0xFFA96600)
private val DashSoftBlue44 = Color(0xFFEAF0FF)
private val DashSoftGreen44 = Color(0xFFE6F5EF)
private val DashSoftAmber44 = Color(0xFFFFF3DF)

private data class DashboardCloud44(
    val portfolio: JSONObject? = null,
    val automation: JSONObject? = null,
    val radar: LayerRadar40? = null,
    val loading: Boolean = true,
    val lastSyncedAt: Long = 0L,
    val errors: List<String> = emptyList()
)

@Composable
fun IntegratedOverview44(
    snapshot: Snapshot?,
    preview: List<PreviewSector>,
    quotes: Map<String, Quote>,
    backendHealth: BackendHealth,
    onNavigate: (Tab) -> Unit
) {
    var generation by remember { mutableIntStateOf(0) }
    var cloud by remember { mutableStateOf(DashboardCloud44()) }

    LaunchedEffect(generation) {
        while (true) {
            val errors = mutableListOf<String>()
            var portfolio = cloud.portfolio
            var automation = cloud.automation
            var radar = cloud.radar
            runCatching { JSONObject(BackendClient.fetchText(DASH_PORTFOLIO_44)) }
                .onSuccess { portfolio = it }
                .onFailure { errors += "组合：${it.message ?: it.javaClass.simpleName}" }
            runCatching { JSONObject(BackendClient.fetchText(DASH_AUTOMATION_44)) }
                .onSuccess { automation = it }
                .onFailure { errors += "自动任务：${it.message ?: it.javaClass.simpleName}" }
            runCatching { fetchLayerRadar40() }
                .onSuccess { radar = it }
                .onFailure { errors += "决策雷达：${it.message ?: it.javaClass.simpleName}" }
            cloud = DashboardCloud44(
                portfolio = portfolio,
                automation = automation,
                radar = radar,
                loading = false,
                lastSyncedAt = System.currentTimeMillis(),
                errors = errors
            )
            delay(30_000)
        }
    }

    val summary = cloud.portfolio?.optJSONObject("summary")
    val report = cloud.portfolio?.optJSONObject("performanceReport")
    val exposure = report?.optJSONObject("exposure")
    val risk = report?.optJSONObject("risk")
    val positions = cloud.portfolio?.optJSONArray("positions")?.length() ?: 0
    val todayTrades = cloud.portfolio?.optJSONArray("todayDecisions")?.length() ?: 0
    val sectors = cloud.radar?.sectors.orEmpty()
    val candidateStocks = cloud.radar?.stocks.orEmpty()
        .sortedWith(
            compareByDescending<LayerStock40> { it.evidenceCount }
                .thenBy { chaseRank44(it.chaseRisk) }
                .thenByDescending { it.turnover ?: -1.0 }
        )
    val indexRows = listOf(
        "上证" to quotes["sh000001"],
        "创业板" to quotes["sz399006"],
        "沪深300" to quotes["sh000300"],
        "中证1000" to quotes["sh000852"]
    )

    LazyColumn(
        modifier = Modifier.fillMaxSize().background(DashBg44),
        contentPadding = PaddingValues(14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item {
            ExecutiveHeader44(
                snapshot = snapshot,
                health = backendHealth,
                automation = cloud.automation,
                radar = cloud.radar,
                loading = cloud.loading,
                onRefresh = { generation++ }
            )
        }

        if (cloud.errors.isNotEmpty()) {
            item {
                Surface(color = DashSoftAmber44, shape = RoundedCornerShape(12.dp)) {
                    Text(
                        "部分数据暂不可用：${cloud.errors.joinToString("；")}。已取得的数据继续显示，不会用空值覆盖缓存。",
                        color = DashAmber44,
                        fontSize = 9.sp,
                        modifier = Modifier.fillMaxWidth().padding(10.dp)
                    )
                }
            }
        }

        item { SelectionStatus45(cloud.portfolio) }
        item { DashboardSectionTitle44("今日筛选决策", "四层状态一次看清") }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                DecisionTile44(
                    title = "市场",
                    value = snapshot?.let { displayRegimeZh27(it.regime) } ?: "等待数据",
                    note = "风险预算待样本外冻结",
                    color = DashAmber44,
                    modifier = Modifier.weight(1f),
                    onClick = { onNavigate(Tab.MARKET) }
                )
                DecisionTile44(
                    title = "板块",
                    value = "${sectors.count { it.stage in setOf("RADAR", "EMERGING", "CONFIRMING") }}个跟踪",
                    note = "潜在→确认→过热",
                    color = DashBlue44,
                    modifier = Modifier.weight(1f),
                    onClick = { onNavigate(Tab.OPPORTUNITY) }
                )
            }
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                DecisionTile44(
                    title = "个股",
                    value = "${candidateStocks.size}只观察",
                    note = "只来自允许板块",
                    color = DashBlue44,
                    modifier = Modifier.weight(1f),
                    onClick = { onNavigate(Tab.OPPORTUNITY) }
                )
                DecisionTile44(
                    title = "影子执行",
                    value = if (automationOk44(cloud.automation)) "后台正常" else "需要检查",
                    note = "${positions}持仓 · 今日${todayTrades}动作",
                    color = if (automationOk44(cloud.automation)) DashGreen44 else DashAmber44,
                    modifier = Modifier.weight(1f),
                    onClick = { onNavigate(Tab.PORTFOLIO) }
                )
            }
        }

        item { DashboardSectionTitle44("市场快照", "指数只描述当下，不替代市场风险模型", { onNavigate(Tab.MARKET) }) }
        item {
            Card44 {
                indexRows.chunked(2).forEachIndexed { rowIndex, row ->
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        row.forEach { (name, quote) ->
                            IndexPulse44(name, quote, Modifier.weight(1f))
                        }
                    }
                    if (rowIndex == 0) {
                        Spacer(Modifier.height(8.dp))
                        HorizontalDivider(color = Color(0xFFE9ECF2))
                        Spacer(Modifier.height(8.dp))
                    }
                }
            }
        }

        item { DashboardSectionTitle44("潜在主线", "优先看资金先行且价格未明显延伸", { onNavigate(Tab.OPPORTUNITY) }) }
        if (sectors.isEmpty()) {
            item { DashboardEmpty44(if (preview.isEmpty()) "等待云端主线雷达" else "正式雷达同步中，基础预览已有${preview.size}个板块") }
        } else {
            items(sectors.take(4), key = { "sector-${it.code}-${it.name}" }) { sector ->
                SectorPulse44(sector, cloud.radar?.date)
            }
        }

        item { DashboardSectionTitle44("板块内个股", "成交结构优先，B0–B3只作为证据标签", { onNavigate(Tab.OPPORTUNITY) }) }
        if (candidateStocks.isEmpty()) {
            item { DashboardEmpty44("当前没有通过板块服从关系的个股观察项") }
        } else {
            items(candidateStocks.take(5), key = { "stock-${it.code}" }) { stock ->
                StockPulse44(stock, cloud.radar?.date)
            }
        }

        item { DashboardSectionTitle44("组合净值与风险", "2000万元容量；100万元阶段历史连续保留", { onNavigate(Tab.PORTFOLIO) }) }
        item {
            Card44 {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    BigMetric44("总资产", money44(num44(summary, "totalAssets")), DashInk44, Modifier.weight(1f))
                    BigMetric44("单位净值", nav44(num44(summary, "unitNav")), DashBlue44, Modifier.weight(1f))
                }
                Spacer(Modifier.height(10.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SmallMetric44("今日", pct44(num44(summary, "todayReturnPct")), pnl44(num44(summary, "todayReturnPct")), Modifier.weight(1f))
                    SmallMetric44("累计", pct44(num44(summary, "cumulativeReturnPct")), pnl44(num44(summary, "cumulativeReturnPct")), Modifier.weight(1f))
                    SmallMetric44("日频回撤", pct44(num44(summary, "maxDrawdownPct")), DashGreen44, Modifier.weight(1f))
                }
                Spacer(Modifier.height(9.dp))
                HorizontalDivider(color = Color(0xFFE9ECF2))
                Spacer(Modifier.height(8.dp))
                KeyRow44("当前容量", money44(num44(summary, "capitalCapacity") ?: num44(summary, "initialCapital")))
                KeyRow44("总仓位", pct44(num44(exposure, "grossExposurePct")))
                KeyRow44("前五集中度", pct44(num44(exposure, "top5ConcentrationPct")))
                KeyRow44(
                    "风险统计",
                    if (risk?.optBoolean("sampleSufficient") == true) "样本已达到年化统计门槛"
                    else "有效日${risk?.optInt("validDailyReturnCount") ?: 0}个，暂不外推年化指标"
                )
                Button(onClick = { onNavigate(Tab.PORTFOLIO) }, modifier = Modifier.fillMaxWidth().padding(top = 5.dp)) {
                    Text("查看持仓、成交与完整报表")
                }
            }
        }

        item { DashboardSectionTitle44("数据与审计", "发生时间、可得时间、来源和版本同时展示") }
        item {
            Card44 {
                KeyRow44("策略快照", snapshot?.let { "${it.date} · ${snapshotAuditLabel(it)}" } ?: "未同步")
                KeyRow44("雷达时点", cloud.radar?.let { "${it.date} ${short44(it.capturedAt)}" } ?: "未同步")
                KeyRow44("后台最近运行", displayTime44(cloud.automation?.optString("lastRunAt")))
                KeyRow44("手机读取来源", backendHealth.source)
                KeyRow44("本次整合同步", if (cloud.lastSyncedAt > 0) clock44(cloud.lastSyncedAt) else "等待首次同步")
                val factorMap = cloud.radar?.factorAvailability.orEmpty()
                Text("因子可用性", color = DashMuted44, fontSize = 9.sp, modifier = Modifier.padding(top = 4.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(top = 4.dp)) {
                    listOf("B0 行情", "B1 两融", "B2 ETF", "B3 主力").forEachIndexed { index, label ->
                        val keyHints = when (index) {
                            0 -> listOf("base", "price", "market")
                            1 -> listOf("margin")
                            2 -> listOf("etf")
                            else -> listOf("flow", "main")
                        }
                        val available = factorMap.any { (key, value) ->
                            keyHints.any { it in key.lowercase() } && value.lowercase() !in setOf("missing", "unavailable", "false")
                        } || (index == 0 && cloud.radar != null) || (index == 3 && sectors.any { it.flowPct != null })
                        FactorBadge44(label, available, Modifier.weight(1f))
                    }
                }
                Text(
                    "两融按T+1可得时间使用；缺失因子不补成中性分。当前自动交易仅为影子模拟，不连接券商。",
                    color = DashMuted44,
                    fontSize = 8.sp,
                    modifier = Modifier.padding(top = 7.dp)
                )
            }
        }
    }
}

@Composable
fun OpportunityHub44(
    snapshot: Snapshot?,
    preview: List<PreviewSector>,
    quotes: Map<String, Quote>,
    now: Long,
    quoteOkAt: Long,
    boardOkAt: Long
) {
    val modes = listOf("板块", "个股", "决策链")
    var mode by remember { mutableStateOf(modes.first()) }
    Column(Modifier.fillMaxSize().background(DashBg44)) {
        HubHeader44("机会中心", "板块准入后再选个股；证据不等于买入结论", modes, mode) { mode = it }
        Box(Modifier.fillMaxWidth().weight(1f)) {
            when (mode) {
                "板块" -> MainlineScreen(snapshot, preview, now, boardOkAt)
                "个股" -> PoolsScreen(snapshot, quotes, now, quoteOkAt)
                else -> LazyColumn(
                    contentPadding = PaddingValues(14.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    item { LayeredDecisionHome40(snapshot, preview, quotes) }
                }
            }
        }
    }
}

@Composable
fun PortfolioHub44() {
    val modes = listOf("自动组合", "手工账本")
    var mode by remember { mutableStateOf(modes.first()) }
    Column(Modifier.fillMaxSize().background(DashBg44)) {
        HubHeader44("组合中心", "云端影子组合与本机手工记录严格分账", modes, mode) { mode = it }
        Box(Modifier.fillMaxWidth().weight(1f)) {
            if (mode == "自动组合") AiShadowPortfolioScreen28() else TradeJournalScreen()
        }
    }
}

@Composable
private fun HubHeader44(title: String, subtitle: String, modes: List<String>, mode: String, onChange: (String) -> Unit) {
    Surface(color = Color.White, tonalElevation = 1.dp) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
            Text(title, color = DashInk44, fontWeight = FontWeight.Bold, fontSize = 16.sp)
            Text(subtitle, color = DashMuted44, fontSize = 9.sp)
            SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                modes.forEachIndexed { index, item ->
                    SegmentedButton(
                        selected = mode == item,
                        onClick = { onChange(item) },
                        shape = SegmentedButtonDefaults.itemShape(index, modes.size),
                        label = { Text(item, fontSize = 10.sp) }
                    )
                }
            }
        }
    }
}

@Composable
private fun ExecutiveHeader44(
    snapshot: Snapshot?,
    health: BackendHealth,
    automation: JSONObject?,
    radar: LayerRadar40?,
    loading: Boolean,
    onRefresh: () -> Unit
) {
    Card(colors = CardDefaults.cardColors(containerColor = DashNavy44), shape = RoundedCornerShape(20.dp)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("a股筛选池", color = Color.White, fontSize = 21.sp, fontWeight = FontWeight.Bold)
                    Text("市场 → 板块 → 个股 → 执行", color = Color(0xFFDCE4FF), fontSize = 10.sp)
                }
                Surface(
                    color = if (health.lastSuccessAt > 0) Color(0xFF246657) else Color(0xFF775524),
                    shape = RoundedCornerShape(20.dp),
                    modifier = Modifier.clickable { onRefresh() }
                ) {
                    Text(
                        if (loading) "同步中" else if (health.usingCache) "缓存模式" else "云端正常",
                        color = Color.White,
                        fontWeight = FontWeight.Bold,
                        fontSize = 9.sp,
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp)
                    )
                }
            }
            HorizontalDivider(color = Color(0xFF35466D))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                HeaderStatus44("策略日", snapshot?.date ?: "—", Modifier.weight(1f))
                HeaderStatus44("雷达", radar?.let { stageStatus44(it.status) } ?: "等待", Modifier.weight(1f))
                HeaderStatus44("自动任务", if (automationOk44(automation)) "正常" else "检查", Modifier.weight(1f))
            }
            Text(
                "计算在云端后台持续运行；打开APK只读取已落库结果。点击右上状态可立即同步。",
                color = Color(0xFFBCC8EC),
                fontSize = 8.sp
            )
        }
    }
}

@Composable
private fun HeaderStatus44(label: String, value: String, modifier: Modifier) {
    Column(modifier) {
        Text(label, color = Color(0xFFAAB7DE), fontSize = 8.sp)
        Text(value, color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
    }
}

@Composable
private fun DecisionTile44(
    title: String,
    value: String,
    note: String,
    color: Color,
    modifier: Modifier,
    onClick: () -> Unit
) {
    Card(
        modifier = modifier.clickable(onClick = onClick),
        colors = CardDefaults.cardColors(containerColor = Color.White),
        shape = RoundedCornerShape(15.dp)
    ) {
        Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(title, color = DashMuted44, fontSize = 9.sp)
            Text(value, color = color, fontSize = 15.sp, fontWeight = FontWeight.Bold, maxLines = 1)
            Text(note, color = DashMuted44, fontSize = 8.sp, maxLines = 1)
        }
    }
}

@Composable
private fun DashboardSectionTitle44(title: String, subtitle: String, onClick: (() -> Unit)? = null) {
    Row(Modifier.fillMaxWidth().padding(top = 3.dp), verticalAlignment = Alignment.Bottom) {
        Column(Modifier.weight(1f)) {
            Text(title, color = DashInk44, fontWeight = FontWeight.Bold, fontSize = 15.sp)
            Text(subtitle, color = DashMuted44, fontSize = 8.sp)
        }
        if (onClick != null) {
            Text("查看全部 ›", color = DashBlue44, fontSize = 9.sp, modifier = Modifier.clickable(onClick = onClick).padding(4.dp))
        }
    }
}

@Composable
private fun Card44(content: @Composable ColumnScope.() -> Unit) {
    Card(colors = CardDefaults.cardColors(containerColor = Color.White), shape = RoundedCornerShape(16.dp)) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(13.dp),
            verticalArrangement = Arrangement.spacedBy(3.dp),
            content = content
        )
    }
}

@Composable
private fun IndexPulse44(name: String, quote: Quote?, modifier: Modifier) {
    Column(modifier) {
        Text(name, color = DashMuted44, fontSize = 9.sp)
        Text(quote?.price?.let { String.format("%.2f", it) } ?: "—", color = DashInk44, fontSize = 14.sp, fontWeight = FontWeight.Bold)
        Text(pct44(quote?.change), color = pnl44(quote?.change), fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun SectorPulse44(sector: LayerSector40, date: String?) {
    Card(
        modifier = Modifier.fillMaxWidth().clickable { DetailNav.openSectorName(sector.name, date) },
        colors = CardDefaults.cardColors(containerColor = Color.White),
        shape = RoundedCornerShape(15.dp)
    ) {
        Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(sector.name, color = DashInk44, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                    Text("${sector.type} · ${stage44(sector.stage)}", color = DashMuted44, fontSize = 9.sp)
                }
                StatusBadge44(chase44(sector.chaseRisk), if (sector.chaseRisk == "HIGH") DashAmber44 else DashGreen44)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(9.dp)) {
                InlineMetric44("涨跌", pct44(sector.changePct), pnl44(sector.changePct), Modifier.weight(1f))
                InlineMetric44("资金", pct44(sector.flowPct), pnl44(sector.flowPct), Modifier.weight(1f))
                InlineMetric44("扩散", plainPct44(sector.breadthPct), DashBlue44, Modifier.weight(1f))
                InlineMetric44("RS20", number44(sector.rs20), DashInk44, Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun StockPulse44(stock: LayerStock40, date: String?) {
    Card(
        modifier = Modifier.fillMaxWidth().clickable { DetailNav.openStock(stock.code, date) },
        colors = CardDefaults.cardColors(containerColor = Color.White),
        shape = RoundedCornerShape(15.dp)
    ) {
        Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("${stock.name} ${stock.code}", color = DashInk44, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                    Text("${stock.sector} · ${stage44(stock.stage)} · ${stock.action}", color = DashMuted44, fontSize = 8.sp)
                }
                StatusBadge44("${stock.evidenceCount}/4证据", if (stock.evidenceCount >= 3) DashGreen44 else DashBlue44)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(9.dp)) {
                InlineMetric44("涨跌", pct44(stock.changePct), pnl44(stock.changePct), Modifier.weight(1f))
                InlineMetric44("成交额", amount44(stock.amount), DashInk44, Modifier.weight(1.15f))
                InlineMetric44("换手", plainPct44(stock.turnover), DashBlue44, Modifier.weight(1f))
                InlineMetric44("量比", number44(stock.volumeRatio), DashBlue44, Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun BigMetric44(label: String, value: String, color: Color, modifier: Modifier) {
    Column(modifier) {
        Text(label, color = DashMuted44, fontSize = 9.sp)
        Text(value, color = color, fontSize = 20.sp, fontWeight = FontWeight.Bold, maxLines = 1)
    }
}

@Composable
private fun SmallMetric44(label: String, value: String, color: Color, modifier: Modifier) {
    Surface(color = color.copy(alpha = 0.08f), shape = RoundedCornerShape(10.dp), modifier = modifier) {
        Column(Modifier.padding(8.dp)) {
            Text(label, color = DashMuted44, fontSize = 8.sp)
            Text(value, color = color, fontSize = 11.sp, fontWeight = FontWeight.Bold, maxLines = 1)
        }
    }
}

@Composable
private fun InlineMetric44(label: String, value: String, color: Color, modifier: Modifier) {
    Column(modifier) {
        Text(label, color = DashMuted44, fontSize = 7.sp)
        Text(value, color = color, fontSize = 9.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
    }
}

@Composable
private fun KeyRow44(label: String, value: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 2.dp), verticalAlignment = Alignment.Top) {
        Text(label, color = DashMuted44, fontSize = 9.sp, modifier = Modifier.width(82.dp))
        Text(value, color = DashInk44, fontSize = 9.sp, fontWeight = FontWeight.Medium, modifier = Modifier.weight(1f))
    }
}

@Composable
private fun StatusBadge44(text: String, color: Color) {
    Surface(color = color.copy(alpha = 0.1f), shape = RoundedCornerShape(20.dp)) {
        Text(text, color = color, fontSize = 8.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(horizontal = 7.dp, vertical = 4.dp))
    }
}

@Composable
private fun FactorBadge44(label: String, available: Boolean, modifier: Modifier) {
    Surface(color = if (available) DashSoftGreen44 else Color(0xFFF0F2F6), shape = RoundedCornerShape(9.dp), modifier = modifier) {
        Text(
            if (available) "$label ✓" else "$label —",
            color = if (available) DashGreen44 else DashMuted44,
            fontSize = 7.sp,
            modifier = Modifier.padding(horizontal = 4.dp, vertical = 6.dp),
            maxLines = 1
        )
    }
}

@Composable
private fun DashboardEmpty44(text: String) {
    Surface(color = Color.White, shape = RoundedCornerShape(14.dp)) {
        Text(text, color = DashMuted44, fontSize = 10.sp, modifier = Modifier.fillMaxWidth().padding(13.dp))
    }
}

private fun num44(o: JSONObject?, key: String): Double? {
    if (o == null || !o.has(key) || o.isNull(key)) return null
    return when (val value = o.opt(key)) {
        is Number -> value.toDouble()
        else -> value?.toString()?.toDoubleOrNull()
    }
}

private fun money44(value: Double?): String = value?.let {
    when {
        abs(it) >= 100_000_000 -> String.format("¥%.2f亿", it / 100_000_000.0)
        abs(it) >= 10_000 -> String.format("¥%.2f万", it / 10_000.0)
        else -> String.format("¥%.2f", it)
    }
} ?: "—"

private fun amount44(value: Double?): String = value?.let {
    when {
        abs(it) >= 100_000_000 -> String.format("%.1f亿", it / 100_000_000.0)
        abs(it) >= 10_000 -> String.format("%.0f万", it / 10_000.0)
        else -> String.format("%.0f", it)
    }
} ?: "—"

private fun pct44(value: Double?): String = value?.let { String.format("%+.2f%%", it) } ?: "—"
private fun plainPct44(value: Double?): String = value?.let { String.format("%.1f%%", it) } ?: "—"
private fun number44(value: Double?): String = value?.let { String.format("%.1f", it) } ?: "—"
private fun nav44(value: Double?): String = value?.let { String.format("%.6f", it) } ?: "—"
private fun pnl44(value: Double?): Color = if ((value ?: 0.0) >= 0) DashRed44 else DashGreen44

private fun displayTime44(value: String?): String = value?.replace('T', ' ')?.take(19)?.ifBlank { "—" } ?: "—"
private fun short44(value: String): String = value.replace('T', ' ').takeLast(8).ifBlank { "—" }
private fun clock44(value: Long): String = java.time.Instant.ofEpochMilli(value).atZone(ZoneId.of("Asia/Shanghai"))
    .toLocalTime().withNano(0).toString()

private fun automationOk44(o: JSONObject?): Boolean = o?.optBoolean("enabled") == true && o.optString("status") != "ERROR"
private fun stageStatus44(value: String): String = when (value.uppercase()) {
    "LIVE", "OK", "READY" -> "已连接"
    "DEGRADED" -> "降级"
    else -> value.ifBlank { "等待" }
}
private fun stage44(value: String): String = when (value.uppercase()) {
    "RADAR" -> "潜在雷达"
    "EMERGING" -> "潜在主线"
    "CONFIRMING" -> "主线确认"
    "ESTABLISHED" -> "已成主线"
    "OVERHEATED" -> "过热"
    "FADING" -> "衰退"
    else -> "观察"
}
private fun chase44(value: String): String = when (value.uppercase()) {
    "LOW" -> "低追高风险"
    "HIGH" -> "高追高风险"
    else -> "中追高风险"
}
private fun chaseRank44(value: String): Int = when (value.uppercase()) {
    "LOW" -> 0
    "MEDIUM" -> 1
    "HIGH" -> 2
    else -> 3
}
