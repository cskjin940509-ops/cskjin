package com.rui.astockstrategy.v6

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.GridView
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.PieChart
import androidx.compose.material.icons.filled.Radar
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
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
import java.net.URLEncoder
import java.nio.charset.Charset
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlin.math.abs

private val Bg = Color(0xFFF5F7FB)
private val Ink = Color(0xFF171A22)
private val Muted = Color(0xFF747B8D)
private val Blue = Color(0xFF3557D4)
private val Up = Color(0xFFD84343)
private val Down = Color(0xFF15966A)
private val Amber = Color(0xFFAE6A00)
private val SoftBlue = Color(0xFFE9EDFF)
private val SoftGreen = Color(0xFFE8F6F0)
private val SoftRed = Color(0xFFFFECEC)
private val CnZone = ZoneId.of("Asia/Shanghai")

data class Quote(
    val symbol: String,
    val name: String,
    val code: String,
    val price: Double?,
    val prev: Double?,
    val change: Double?,
    val high: Double?,
    val low: Double?,
    val amount: Double?,
    val quoteTime: String?
)

data class Board(
    val code: String,
    val name: String,
    val change: Double?,
    val amount: Double?,
    val flow: Double?,
    val flowPct: Double?,
    val up: Int,
    val down: Int,
    val flat: Int,
    val type: String
)

data class OfficialSector(
    val code: String,
    val name: String,
    val type: String?,
    val score: Double?,
    val status: String?,
    val changePct: Double?,
    val amount: Double?,
    val mainNet资金流强度: Double?,
    val main资金流强度Pct: Double?,
    val breadthPct: Double?,
    val rs20: Double?,
    val rs60: Double?,
    val mta: String?,
    val confidence: String?,
    val reason: String?
)

data class StockMeta(
    val code: String,
    val name: String?,
    val sector: String?,
    val rs: Double?,
    val mta: String?,
    val score: Double?,
    val reason: String?,
    val selectionPrice: Double?,
    val confidence: String?,
    val dayChangePct: Double?,
    val dayOpen: Double?,
    val dayClose: Double?,
    val dayHigh: Double?,
    val dayLow: Double?,
    val dayRangePct: Double?,
    val amount: Double?,
    val turnover: Double?,
    val mainNet资金流强度: Double?,
    val main资金流强度Pct: Double?,
    val rs60: Double?,
    val priceProviders: List<String>,
    val priceMaxRelDiff: Double?
)

data class Snapshot(
    val date: String,
    val status: String,
    val regime: String,
    val strategyVersion: String?,
    val auditStatus: String?,
    val performanceEligible: Boolean,
    val auditIssues: List<String>,
    val selectedSectors: List<OfficialSector>,
    val factorAvailability: Map<String, String>,
    val trackingUse: String?,
    val mainlines: List<String>,
    val pools: Map<String, List<String>>,
    val stocks: Map<String, StockMeta>,
    val poolPerformance: Map<String, JSONObject>,
    val sectorPerformance: Map<String, JSONObject>,
    val stockPerformance: Map<String, JSONObject>,
    val note: String?
)

data class PreviewSector(
    val board: Board,
    val score: Double,
    val state: String,
    val momentum: Double,
    val breadth: Double,
    val flowScore: Double
)


enum class Tab(val label: String, val icon: ImageVector) {
    TODAY("总览", Icons.Default.Home),
    MARKET("市场", Icons.Default.GridView),
    OPPORTUNITY("机会", Icons.Default.Radar),
    PORTFOLIO("组合", Icons.Default.PieChart),
    HISTORY("研究", Icons.Default.CalendarMonth)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AStockV6() {
    val uriHandler = LocalUriHandler.current
    var tab by remember { mutableStateOf(Tab.TODAY) }
    var snapshots by remember { mutableStateOf<List<Snapshot>>(emptyList()) }
    var selectedDate by remember { mutableStateOf<String?>(null) }
    var quotes by remember { mutableStateOf<Map<String, Quote>>(emptyMap()) }
    var industries by remember { mutableStateOf<List<Board>>(emptyList()) }
    var concepts by remember { mutableStateOf<List<Board>>(emptyList()) }
    var quoteOkAt by remember { mutableLongStateOf(0L) }
    var boardOkAt by remember { mutableLongStateOf(0L) }
    var tick by remember { mutableLongStateOf(System.currentTimeMillis()) }
    var quoteError by remember { mutableStateOf<String?>(null) }
    var boardError by remember { mutableStateOf<String?>(null) }
    var snapshotError by remember { mutableStateOf<String?>(null) }
    var radarError by remember { mutableStateOf<String?>(null) }
    var preview by remember { mutableStateOf<List<PreviewSector>>(emptyList()) }
    var refreshGeneration by remember { mutableIntStateOf(0) }
    val backendHealth by BackendClient.health.collectAsState()

    val latest = snapshots.maxByOrNull { it.date }
    val active = selectedDate?.let { date -> snapshots.firstOrNull { it.date == date } } ?: latest
    val activeCodes = active?.pools?.values?.flatten()?.distinct().orEmpty()
    val detailSector = DetailNav.sector
    val detailStock = DetailNav.stockCode

    LaunchedEffect(Unit) {
        while (true) {
            tick = System.currentTimeMillis()
            delay(1000)
        }
    }

    LaunchedEffect(refreshGeneration) {
        while (true) {
            runCatching { DataApi.fetchSnapshots() }
                .onSuccess {
                    if (it.isNotEmpty()) {
                        snapshots = it
                        snapshotError = null
                    } else {
                        snapshotError = "后端返回空快照"
                    }
                }
                .onFailure { snapshotError = it.message ?: it.javaClass.simpleName }
            runCatching { ResilientDataApi.fetchBoardsPair() }.onSuccess { pair ->
                industries = pair.first
                concepts = pair.second
                boardOkAt = System.currentTimeMillis()
                boardError = null
            }.onFailure {
                boardError = it.javaClass.simpleName
            }
            runCatching { DataApi.fetchPrecomputedPreview() }
                .onSuccess {
                    preview = it
                    radarError = null
                }
                .onFailure { radarError = it.message ?: it.javaClass.simpleName }
            delay(30000)
        }
    }

    LaunchedEffect(activeCodes.joinToString(","), refreshGeneration) {
        while (true) {
            val symbols = (listOf("sh000001", "sz399006", "sh000688", "sh000300", "sh000852") + activeCodes.map(::symbol)).distinct()
            if (symbols.isNotEmpty()) {
                runCatching { ResilientDataApi.fetchQuotes(symbols) }
                    .onSuccess {
                        if (it.isNotEmpty()) {
                            quotes = it
                            quoteOkAt = System.currentTimeMillis()
                            quoteError = null
                        }
                    }
                    .onFailure { quoteError = it.javaClass.simpleName }
            }
            delay(30000)
        }
    }

    MaterialTheme(
        colorScheme = lightColorScheme(primary = Blue, background = Bg, surface = Color.White, onSurface = Ink)
    ) {
        Scaffold(
            containerColor = Bg,
            topBar = {
                TopAppBar(
                    title = {
                        Column {
                            Text(
                                when (tab) {
                                    Tab.TODAY -> "a股筛选池"
                                    Tab.MARKET -> "市场全景"
                                    Tab.OPPORTUNITY -> "板块与个股"
                                    Tab.PORTFOLIO -> "组合与风控"
                                    Tab.HISTORY -> "历史研究"
                                },
                                fontWeight = FontWeight.Bold
                            )
                            Text(
                                active?.let { "${it.date} · ${snapshotAuditLabel(it)} · ${displayRegimeZh27(it.regime)}" } ?: "等待策略快照",
                                fontSize = 11.sp,
                                color = if (active?.auditStatus == "Verified") Down else Amber
                            )
                        }
                    },
                    actions = {
                        LivePill(
                            label = when {
                                backendHealth.usingCache -> "缓存可用"
                                backendHealth.lastSuccessAt > 0 -> "云端已同步"
                                else -> "等待后端"
                            },
                            ok = backendHealth.lastSuccessAt > 0
                        )
                        TextButton(onClick = { uriHandler.openUri("https://github.com/cskjin940509-ops/cskjin/releases/latest") }) { Text("更新", fontSize = 12.sp) }
                        IconButton(onClick = { refreshGeneration++ }) {
                            Icon(Icons.Default.Refresh, contentDescription = "立即同步")
                        }
                    }
                )
            },
            bottomBar = {
                NavigationBar {
                    Tab.entries.forEach { item ->
                        NavigationBarItem(
                            selected = tab == item,
                            onClick = {
                                DetailNav.reset()
                                tab = item
                                if (item != Tab.HISTORY) selectedDate = null
                            },
                            icon = { Icon(item.icon, null) },
                            label = { Text(item.label) }
                        )
                    }
                }
            }
        ) { pad ->
            Box(Modifier.padding(pad).fillMaxSize()) {
                when {
                    detailStock != null -> {
                        val detailSnapshot = DetailNav.stockDate?.let { d -> snapshots.firstOrNull { it.date == d } } ?: active
                        StockDetailScreen(detailStock, detailSnapshot, quotes[symbol(detailStock)]) { DetailNav.back() }
                    }
                    detailSector != null -> {
                        val detailSnapshot = detailSector.date?.let { d -> snapshots.firstOrNull { it.date == d } } ?: active
                        SectorDetailScreen(detailSector, detailSnapshot) { DetailNav.back() }
                    }
                    else -> when (tab) {
                    Tab.TODAY -> IntegratedOverview44(active, preview, quotes, backendHealth) { tab = it }
                    Tab.MARKET -> MarketScreen(quotes, industries, concepts, tick, quoteOkAt, boardOkAt, quoteError, boardError)
                    Tab.OPPORTUNITY -> OpportunityHub44(active, preview, quotes, tick, quoteOkAt, boardOkAt)
                    Tab.PORTFOLIO -> PortfolioHub44()
                    Tab.HISTORY -> HistoryHub32(snapshots, active, quotes, selectedDate) { selectedDate = it }
                }
                }
            }
        }
    }
}

@Composable
fun TodayScreen(
    s: Snapshot?,
    preview: List<PreviewSector>,
    quotes: Map<String, Quote>,
    now: Long,
    quoteOkAt: Long,
    boardOkAt: Long,
    backendHealth: BackendHealth,
    snapshotError: String?,
    radarError: String?,
    quoteError: String?,
    boardError: String?
) {
    var showLegacyTools by remember { mutableStateOf(false) }
    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { BackendStatusCard41(backendHealth, snapshotError, radarError, quoteError, boardError) }
        item { LayeredDecisionHome40(s, preview, quotes) }

        item {
            Card(shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
                Column(Modifier.fillMaxWidth().padding(13.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                    Text("兼容工具", fontWeight = FontWeight.Bold)
                    Text("保留v3.4盘前池、尾盘判断和执行记录，但它们不覆盖v4.3分层准入。", color = Muted, fontSize = 9.sp)
                    OutlinedButton(onClick = { showLegacyTools = !showLegacyTools }, modifier = Modifier.fillMaxWidth()) {
                        Text(if (showLegacyTools) "收起旧版辅助模块" else "展开旧版辅助模块")
                    }
                }
            }
        }

        if (showLegacyTools) {
            item { Notice("以下模块仅作兼容观察与模拟记录；旧总分、旧综合池和动态目标不得绕过市场→板块→个股的准入顺序。") }
            item { PremarketPredictionPanel34() }
            item { EarlyRadarSummary() }
            item { SlowMoneyPanel31() }
            item { TailDecisionPanel() }
            item { ExecutionPanel() }
            item { ShapeSetupPanel() }

            if (!marketOpenNow()) {
                item { PostCloseDashboard(quotes, preview, s) }
            } else {
                item { Title("旧版盘中预览") }
                if (preview.isEmpty()) item { EmptyCard("等待实时板块数据") }
                else items(preview.take(5)) { PreviewRow(it) }
            }

            item { Title("正式冻结快照（兼容）") }
            if (s == null) {
                item { EmptyCard("正式策略尚未同步") }
            } else {
                item { DataCoverageCard(s) }
                if (!s.performanceEligible) item { AuditWarning(s) }
                val legacy = s.pools["B4"].orEmpty()
                if (legacy.isNotEmpty()) {
                    item { Notice("旧B4名单只作为历史证据标签展示，不等于v4.3买入池。") }
                    items(legacy.take(10)) { code -> StockLiveRow(code, s, quotes[symbol(code)]) }
                }
            }
        }
    }
}

@Composable
private fun BackendStatusCard41(
    health: BackendHealth,
    snapshotError: String?,
    radarError: String?,
    quoteError: String?,
    boardError: String?
) {
    Card(shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.fillMaxWidth().padding(13.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("后台与数据库", fontWeight = FontWeight.Bold)
                    Text("定时任务独立运行；打开APK只同步结果，不触发选板块或选股计算", color = Muted, fontSize = 9.sp)
                }
                LivePill(
                    label = if (health.usingCache) "本地缓存" else if (health.lastSuccessAt > 0) "云端正常" else "未连接",
                    ok = health.lastSuccessAt > 0
                )
            }
            Key("计算位置", "云端定时任务")
            Key("云端数据时间", health.lastServerTime?.replace('T', ' ')?.take(19) ?: "等待首次同步")
            Key("当前读取", health.source)
            if (health.usingCache) {
                Notice("云端接口暂时不可用，正在展示本机缓存中最后一次成功数据；不会用空值覆盖旧数据。")
            }
            val errors = listOfNotNull(snapshotError, radarError, quoteError, boardError, health.lastError).distinct()
            if (errors.isNotEmpty()) {
                Text("异常：${errors.joinToString("；")}", color = Amber, fontSize = 8.sp, maxLines = 3)
            }
        }
    }
}

@Composable
fun StatusCard(now: Long, quoteOkAt: Long, boardOkAt: Long, s: Snapshot?) {
    Card(shape = RoundedCornerShape(18.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.padding(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("数据状态", fontWeight = FontWeight.Bold)
                    Text("实时行情、板块数据与策略快照分层显示", fontSize = 10.sp, color = Muted)
                }
                Text(chinaClock(), fontSize = 12.sp, fontWeight = FontWeight.Bold)
            }
            Spacer(Modifier.height(10.dp))
            Key("个股/指数", marketStateLabel(now, quoteOkAt, emptyMap()))
            Key("行业/概念", freshnessLabel(now, boardOkAt, 70000, "实时", "已过期"))
            Key("正式策略", s?.let { "${it.date} ${snapshotAuditLabel(it)}" } ?: "未同步")
            Key("盘中主线", if (marketOpenNow()) "实时预览" else "收盘预览")
            Key("行情来源", ResilientDataApi.quoteSource)
            Key("板块来源", ResilientDataApi.boardSource)
            YunaiGatewayStatusLine()
        }
    }
}

@Composable
fun MarketScreen(
    quotes: Map<String, Quote>,
    industries: List<Board>,
    concepts: List<Board>,
    now: Long,
    quoteOkAt: Long,
    boardOkAt: Long,
    quoteError: String?,
    boardError: String?
) {
    var type by remember { mutableStateOf("行业") }
    var sort by remember { mutableStateOf("涨跌") }
    val src = if (type == "行业") industries else concepts
    val sorted = when (sort) {
        "资金" -> src.sortedByDescending { it.flow ?: Double.NEGATIVE_INFINITY }
        "广度" -> src.sortedByDescending(::breadth)
        else -> src.sortedByDescending { it.change ?: Double.NEGATIVE_INFINITY }
    }
    val indexSymbols = listOf("sh000001", "sz399006", "sh000688", "sh000300", "sh000852")

    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                LiveBadge("行情", ResilientDataApi.quoteSource, quoteOkAt > 0, Modifier.weight(1f))
                LiveBadge("板块", ResilientDataApi.boardSource, boardOkAt > 0, Modifier.weight(1f))
            }
        }
        if (quoteError != null || boardError != null) {
            item { Notice("行情或板块数据源出现异常；页面会明确标记数据新鲜度，不会把旧数据伪装成实时行情。") }
        }
        item { Title("指数行情") }
        items(indexSymbols.chunked(2)) { pair ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                pair.forEach { sym -> IndexCard(quotes[sym], Modifier.weight(1f)) }
                if (pair.size == 1) Spacer(Modifier.weight(1f))
            }
        }
        item { Choice(listOf("行业", "概念"), type) { type = it } }
        item { Choice(listOf("涨跌", "资金", "广度"), sort) { sort = it } }
        item { Title(if (marketOpenNow()) "实时${type}热力图" else "收盘${type}热力图") }
        if (sorted.isEmpty()) {
            item { EmptyCard("当前没有取得板块实时数据") }
        } else {
            items(sorted.take(80).chunked(2)) { pair ->
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    pair.forEach { b -> HeatTile(b, Modifier.weight(1f)) }
                    if (pair.size == 1) Spacer(Modifier.weight(1f))
                }
            }
        }
    }
}

@Composable
fun MainlineScreen(s: Snapshot?, preview: List<PreviewSector>, now: Long, boardOkAt: Long) {
    var mode by remember { mutableStateOf("盘中预览") }
    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { Choice(listOf("盘中预览", "正式冻结"), mode) { mode = it } }
        if (mode == "盘中预览") {
            item { Notice("APK每30秒同步云端板块候选；状态由后台任务预计算，打开软件不会重算股票池。") }
            item { LiveBadge("主线预览", freshnessLabel(now, boardOkAt, 70000, "实时", "已过期"), now - boardOkAt <= 70000, Modifier.fillMaxWidth()) }
            if (preview.isEmpty()) item { EmptyCard("等待实时板块数据") }
            else items(preview.take(12)) { PreviewRadar(it) }
        } else {
            if (s == null) {
                item { EmptyCard("正式策略尚未同步") }
            } else {
                item { Notice("${s.date} ${snapshotAuditLabel(s)}：确认主线和正式候选板块分开显示，不把观察板块冒充确认主线。") }
                if (!s.performanceEligible) item { AuditWarning(s) }
                item { CardBlock { Key("确认主线", s.mainlines.joinToString(" / ").ifBlank { "无" }); Key("候选板块数", s.selectedSectors.size.toString()) } }
                if (s.mainlines.isEmpty()) item { Notice("今日没有板块达到“确认主线”阈值；下面仍展示收盘扫描得到的正式候选板块。") }
                if (s.selectedSectors.isEmpty()) {
                    if (s.mainlines.isEmpty()) item { EmptyCard("该日没有达标板块") }
                    else items(s.mainlines) { name -> OfficialMainlineFallback(name, s.date) }
                } else {
                    items(s.selectedSectors) { OfficialSectorRow(it, s.date) }
                }
            }
        }
    }
}

@Composable
fun PoolsScreen(s: Snapshot?, quotes: Map<String, Quote>, now: Long, quoteOkAt: Long) {
    if (s == null) { Empty("暂无正式股票池快照"); return }
    var pool by remember(s.date) { mutableStateOf("B0") }
    val codes = s.pools[pool].orEmpty()
    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
        item { PoolSelector(pool) { pool = it } }
        item { Notice("${poolTitle(pool)} 来自 ${s.date} 的 ${snapshotAuditLabel(s)}；这里是证据分组与审计视图，不是按总分给出的买入池。") }
        item { SameDayPoolCard(s, pool) }
        item { LiveBadge("行情", freshnessLabel(now, quoteOkAt, 15000, "实时", "已过期"), marketStateOk(now, quoteOkAt), Modifier.fillMaxWidth()) }
        if (codes.isEmpty()) item { EmptyCard("${poolTitle(pool)} 当前为空；必要因子缺失或没有共同达标股票时不会补假信号。") }
        else items(codes) { code -> StockLiveRow(code, s, quotes[symbol(code)]) }
        item { ForwardTrackingCard(s, pool) }
    }
}

@Composable
fun HistoryScreen(
    all: List<Snapshot>,
    s: Snapshot?,
    quotes: Map<String, Quote>,
    selectedDate: String?,
    onDate: (String) -> Unit
) {
    if (all.isEmpty()) { Empty("历史数据库为空"); return }
    val sorted = all.sortedByDescending { it.date }
    var pool by remember(s?.date) { mutableStateOf("B0") }
    val snap = s ?: sorted.first()
    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { Title("历史回溯") }
        item { Notice("信号日行情、冻结名单和次日开盘起的 后续收益跟踪 分开显示。历史详情的K线严格截止所选日期。") }
        items(sorted.take(40).chunked(4)) { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                row.forEach { item -> DateChip(item, selectedDate == item.date || (selectedDate == null && item.date == snap.date), Modifier.weight(1f)) { onDate(item.date) } }
                repeat(4 - row.size) { Spacer(Modifier.weight(1f)) }
            }
        }
        item { CardBlock { Key("日期", snap.date); Key("状态", snapshotAuditLabel(snap)); Key("市场状态", displayRegimeZh27(snap.regime)); Key("确认主线", snap.mainlines.joinToString(" / ").ifBlank { "无" }); Key("正式候选", snap.selectedSectors.take(4).joinToString(" / ") { it.name }.ifBlank { "无" }) } }
        if (!snap.performanceEligible) item { AuditWarning(snap) }
        item { HistoricalMarketReplay(snap.date) }
        if (snap.selectedSectors.isNotEmpty()) {
            item { Title("当日正式候选板块") }
            items(snap.selectedSectors.take(6)) { OfficialSectorRow(it, snap.date) }
        }
        item { Title("策略回顾") }
        item { PoolSelector(pool) { pool = it } }
        item { SameDayPoolCard(snap, pool) }
        val codes = snap.pools[pool].orEmpty()
        if (codes.isEmpty()) item { EmptyCard("${poolTitle(pool)} 当日为空") }
        else items(codes) { code -> HistoryStockRow(code, snap, quotes[symbol(code)]) }
        item { ForwardTrackingCard(snap, pool) }
        snap.note?.let { item { Notice(it) } }
    }
}

@Composable
fun PreviewRow(p: PreviewSector) {
    Card(Modifier.fillMaxWidth().clickable { DetailNav.openSector(p.board) }, shape = RoundedCornerShape(16.dp)) {
        Column(Modifier.padding(13.dp)) {
            Row {
                Column(Modifier.weight(1f)) {
                    Text(p.board.name, fontWeight = FontWeight.Bold)
                    Text("${p.board.type} · ${displayPreviewStateZh27(p.state)}", fontSize = 10.sp, color = Blue)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(p.board.change?.let(::pct) ?: "—", color = p.board.change?.let(::pnl) ?: Muted, fontWeight = FontWeight.Bold)
                    Text("综合评分 ${String.format("%.0f", p.score)}", fontSize = 10.sp, color = Muted)
                }
            }
            Spacer(Modifier.height(8.dp))
            ProgressLine("后台吸筹分", p.momentum)
            ProgressLine("上涨扩散度", p.breadth)
            ProgressLine("资金净流占比", p.flowScore)
        }
    }
}

@Composable
fun PreviewRadar(p: PreviewSector) {
    Card(Modifier.fillMaxWidth().clickable { DetailNav.openSector(p.board) }, shape = RoundedCornerShape(16.dp)) {
        Column(Modifier.padding(14.dp)) {
            Row {
                Column(Modifier.weight(1f)) {
                    Text(p.board.name, fontWeight = FontWeight.Bold)
                    Text(displayPreviewStateZh27(p.state), color = if (p.state in setOf("CONFIRMING", "ESTABLISHED")) Down else Amber, fontSize = 10.sp)
                }
                Text("${String.format("%.0f", p.score)}", fontSize = 20.sp, fontWeight = FontWeight.Bold)
            }
            Spacer(Modifier.height(8.dp))
            ProgressLine("后台吸筹分", p.momentum)
            ProgressLine("上涨扩散度", p.breadth)
            ProgressLine("资金净流占比", p.flowScore)
            Key("涨跌", p.board.change?.let(::pct) ?: "—")
            Key("成交额", p.board.amount?.let(::money) ?: "—")
            Key("主力净流", p.board.flow?.let(::signedMoney) ?: "—")
        }
    }
}

@Composable
fun ProgressLine(name: String, value: Double) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(vertical = 2.dp)) {
        Text(name, Modifier.width(76.dp), fontSize = 10.sp, color = Muted)
        LinearProgressIndicator(progress = { (value / 100.0).coerceIn(0.0, 1.0).toFloat() }, modifier = Modifier.weight(1f).height(6.dp))
        Spacer(Modifier.width(8.dp))
        Text(String.format("%.0f", value), fontSize = 10.sp)
    }
}

@Composable
fun StockLiveRow(code: String, s: Snapshot, q: Quote?) {
    val meta = s.stocks[code]
    val perf = s.stockPerformance[code]
    val displayPrice = q?.price ?: meta?.dayClose ?: meta?.selectionPrice
    val dayMove = q?.change ?: meta?.dayChangePct
    val dayHigh = q?.high ?: meta?.dayHigh
    val dayLow = q?.low ?: meta?.dayLow
    val dayRange = if (dayHigh != null && dayLow != null && dayLow > 0) (dayHigh / dayLow - 1.0) * 100.0 else meta?.dayRangePct
    val selection = meta?.selectionPrice
    val postSignalMove = if (selection != null && selection > 0 && displayPrice != null) (displayPrice / selection - 1.0) * 100.0 else null
    Card(Modifier.fillMaxWidth().clickable { DetailNav.openStock(code, s.date) }, shape = RoundedCornerShape(15.dp)) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Row {
                Column(Modifier.weight(1f)) {
                    Text(meta?.name ?: q?.name ?: code, fontWeight = FontWeight.Bold)
                    Text("$code · ${meta?.sector ?: "未分类"} · 点开查看并交易", fontSize = 10.sp, color = Muted)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(displayPrice?.let { String.format("%.2f", it) } ?: "数据未同步", fontWeight = FontWeight.Bold)
                    Text(dayMove?.let(::pct) ?: "当日涨跌未同步", color = dayMove?.let(::pnl) ?: Muted, fontSize = 11.sp)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("冻结收盘 ${selection?.let { String.format("%.2f", it) } ?: "未同步"}", fontSize = 9.sp, color = Muted)
                Text("相对冻结价 ${postSignalMove?.let { String.format("%+.2f%%", it) } ?: "待下一行情"}", fontSize = 9.sp, color = postSignalMove?.let(::pnl) ?: Muted)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("当日最高 ${dayHigh?.let { String.format("%.2f", it) } ?: "未同步"}", fontSize = 9.sp, color = Muted)
                Text("当日最低 ${dayLow?.let { String.format("%.2f", it) } ?: "未同步"}", fontSize = 9.sp, color = Muted)
                Text("理论高低区间 ${dayRange?.let { String.format("%.2f%%", it) } ?: "未同步"}", fontSize = 9.sp, color = Muted)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("主力 ${meta?.mainNet资金流强度?.let(::signedMoney) ?: "未同步"}", fontSize = 9.sp, color = Muted)
                Text("换手 ${meta?.turnover?.let { String.format("%.2f%%", it) } ?: "未同步"}", fontSize = 9.sp, color = Muted)
            }
            TradeAssistStrip(code, s, meta, q)
            if (perf != null && perf.length() > 0) {
                Text("策略后续收益 ${detailCurrentReturn(perf)} · ${if (s.performanceEligible) "已纳入统计" else "参考展示"}", fontSize = 9.sp, color = Blue)
            } else {
                Text(if (s.date == LocalDate.now(CnZone).toString()) "策略收益从下一交易日可成交开盘开始" else "后续收益尚未同步", fontSize = 9.sp, color = Muted)
            }
        }
    }
}

@Composable
fun HistoryStockRow(code: String, s: Snapshot, q: Quote?) {
    val meta = s.stocks[code]
    val perf = s.stockPerformance[code]
    Card(Modifier.fillMaxWidth().clickable { DetailNav.openStock(code, s.date) }, shape = RoundedCornerShape(15.dp)) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Row {
                Column(Modifier.weight(1f)) {
                    Text(meta?.name ?: q?.name ?: code, fontWeight = FontWeight.Bold)
                    Text("$code · 信号日 ${meta?.dayChangePct?.let(::pct) ?: "涨跌未同步"}", fontSize = 10.sp, color = Muted)
                }
                Text(s.pools.filterValues { code in it }.keys.sorted().joinToString(" "), fontSize = 10.sp, color = Blue)
            }
            if (perf != null && perf.length() > 0) {
                TrackingStrip(perf)
            DailyTrackingStrip25(perf)
                Text("当前跟踪 ${detailCurrentReturn(perf)}${if (!s.performanceEligible) " · 参考，不计入策略统计" else ""}", fontSize = 9.sp, color = if (s.performanceEligible) Blue else Amber)
            } else {
                Text(if (s.date == LocalDate.now(CnZone).toString()) "策略收益从下一交易日开盘开始，今天尚未产生" else "后续收益跟踪 尚未同步", fontSize = 9.sp, color = Muted)
            }
        }
    }
}

@Composable
fun IndexCard(q: Quote?, modifier: Modifier) {
    Card(modifier, shape = RoundedCornerShape(14.dp)) {
        Column(Modifier.padding(11.dp)) {
            Text(q?.name ?: "—", fontSize = 11.sp, color = Muted)
            Text(q?.price?.let { String.format("%.2f", it) } ?: "—", fontWeight = FontWeight.Bold, fontSize = 16.sp)
            Text(q?.change?.let(::pct) ?: "—", color = q?.change?.let(::pnl) ?: Muted, fontSize = 11.sp)
            Text(q?.quoteTime?.let { "行情时间 $it" } ?: "行情时间不可用", fontSize = 8.sp, color = Muted)
        }
    }
}

@Composable
fun HeatTile(b: Board, modifier: Modifier) {
    val bg = when {
        (b.change ?: 0.0) > 2 -> SoftRed
        (b.change ?: 0.0) > 0 -> Color(0xFFFFF5F2)
        (b.change ?: 0.0) < -2 -> Color(0xFFE4F4ED)
        (b.change ?: 0.0) < 0 -> Color(0xFFEEF8F4)
        else -> Color.White
    }
    Card(modifier.clickable { DetailNav.openSector(b) }, colors = CardDefaults.cardColors(containerColor = bg), shape = RoundedCornerShape(14.dp)) {
        Column(Modifier.padding(11.dp)) {
            Text(b.name, fontWeight = FontWeight.Bold, fontSize = 13.sp, maxLines = 1)
            Text(b.change?.let(::pct) ?: "—", color = b.change?.let(::pnl) ?: Muted, fontWeight = FontWeight.Bold)
            Text("广度 ${String.format("%.0f%%", breadth(b))}", fontSize = 9.sp, color = Muted)
            Text(b.flow?.let { "资金 ${signedMoney(it)} · 点开查看并交易" } ?: "资金 — · 点开查看并交易", fontSize = 9.sp, color = Muted, maxLines = 1)
        }
    }
}

@Composable
fun DateChip(s: Snapshot, selected: Boolean, modifier: Modifier, onClick: () -> Unit) {
    Card(
        modifier.clickable(onClick = onClick),
        colors = CardDefaults.cardColors(containerColor = if (selected) SoftBlue else if (s.auditStatus == "Verified") SoftGreen else Color(0xFFFFF1E7)),
        shape = RoundedCornerShape(12.dp)
    ) {
        Column(Modifier.padding(8.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(s.date.substring(5), fontWeight = FontWeight.Bold, fontSize = 11.sp)
            Text(when (s.auditStatus) { "Verified" -> "已核对"; "PartiallyVerified" -> "部分核对"; else -> "未核对" }, fontSize = 8.sp, color = if (s.auditStatus == "Verified") Down else Amber)
        }
    }
}

@Composable
fun LivePill(label: String, ok: Boolean) {
    Surface(color = if (ok) SoftGreen else Color(0xFFFFF0E0), shape = RoundedCornerShape(20.dp)) {
        Text(label, modifier = Modifier.padding(horizontal = 9.dp, vertical = 5.dp), fontSize = 9.sp, color = if (ok) Down else Amber)
    }
}

@Composable
fun LiveBadge(title: String, state: String, ok: Boolean, modifier: Modifier) {
    Card(modifier, colors = CardDefaults.cardColors(containerColor = if (ok) SoftGreen else Color(0xFFFFF1E7)), shape = RoundedCornerShape(14.dp)) {
        Column(Modifier.padding(10.dp)) {
            Text(title, fontSize = 9.sp, color = Muted)
            Text(state, fontWeight = FontWeight.Bold, color = if (ok) Down else Amber)
        }
    }
}

fun snapshotAuditLabel(s: Snapshot): String = when (s.auditStatus) {
    "Verified" -> "已核对"
    "PartiallyVerified" -> "部分核对 / 可参考跟踪"
    "LegacyUnverified" -> "未验证"
    else -> "待核对"
}

@Composable
fun AuditWarning(s: Snapshot) {
    Surface(color = Color(0xFFFFF1E7), shape = RoundedCornerShape(14.dp)) {
        Column(Modifier.fillMaxWidth().padding(11.dp)) {
            Text("⚠ ${snapshotAuditLabel(s)}", fontWeight = FontWeight.Bold, color = Amber)
            Text(if (s.auditStatus == "PartiallyVerified") "该批次已完成可恢复数据核查，可展示经入场价验证的参考收益跟踪；因缺少原始 时点冻结 成分等证据，暂不纳入胜率、超额收益或因子成绩统计。" else "该批次保留原冻结名单用于审计；证据不足时不纳入胜率、超额收益或池间比较。", fontSize = 10.sp, color = Ink)
            if (s.auditIssues.isNotEmpty()) Text(s.auditIssues.joinToString(" · ") { auditIssueZh(it) }, fontSize = 8.sp, color = Muted, maxLines = 3)
        }
    }
}

@Composable
fun AuditPerformanceBlocked() {
    Notice("该批次尚未通过数据审计，历史收益只保留原始记录，不进入模型表现统计。")
}

fun factorTextZh(v: String): String = v
    .replace("B123", "两融、ETF与主力三类交叉证据")
    .replace("B12", "两融与ETF交叉证据")
    .replace("B13", "两融与主力交叉证据")
    .replace("B23", "ETF与主力交叉证据")
    .replace("B0", "行情、成交与广度证据")
    .replace("B1", "两融证据")
    .replace("B2", "ETF一级份额证据")
    .replace("B3", "主力或其他资金证据")
    .replace("B4", "旧综合标签（仅兼容研究）")
    .replace("ETF", "交易型开放式指数基金")

fun auditIssueZh(v: String): String = when {
    v.startsWith("raw-price-cross-source-incomplete") -> "原始价格跨数据源核对不完整" + v.substringAfter(':', "").let { if (it.isBlank()) "" else "（$it）" }
    v == "point-in-time-constituent-snapshot-missing" -> "缺少时点成分股冻结快照"
    v == "missing-strategy-version" -> "缺少策略版本记录"
    v.startsWith("missing-stock-metadata") -> "个股元数据缺失" + v.substringAfter(':', "").let { if (it.isBlank()) "" else "（$it）" }
    v.contains("margin", true) -> "两融数据来源证据不足"
    v.contains("etf", true) -> "指数基金一级申赎数据来源证据不足"
    v.contains("price", true) -> "价格数据核对证据不足"
    v.contains("source", true) || v.contains("provenance", true) -> "数据来源证据不足"
    else -> "数据审计项待核对"
}

@Composable
fun PerformanceCard(title: String, p: JSONObject?) {
    CardBlock {
        Text(title, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(6.dp))
        if (p == null || p.length() == 0) Text("尚未成熟 / 尚未同步", color = Muted, fontSize = 12.sp)
        else { TrackingStrip(p); PoolNavStrip25(p) }
    }
}

@Composable
fun TrackingStrip(p: JSONObject?) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(5.dp)) {
        listOf("1D" to "1日", "5D" to "5日", "10D" to "10日", "20D" to "20日", "60D" to "60日").forEach { (h, hLabel) ->
            Column(
                Modifier.weight(1f).background(Color(0xFFF3F5F9), RoundedCornerShape(8.dp)).padding(5.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(hLabel, fontSize = 8.sp, color = Muted)
                Text(extractHorizon(p, h), fontSize = 9.sp, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

fun poolTitle(pool: String): String = when (pool) {
    "B0" -> "B0 行情/成交/广度证据"
    "B1" -> "B1 两融证据"
    "B2" -> "B2 ETF一级份额证据"
    "B3" -> "B3 主力或其他资金证据"
    "B12" -> "B12 两融与ETF交叉证据"
    "B13" -> "B13 两融与主力交叉证据"
    "B23" -> "B23 ETF与主力交叉证据"
    "B123" -> "B123 三类资金共同确认"
    "B4" -> "旧综合标签（仅兼容研究）"
    else -> pool
}

@Composable
fun PoolSelector(value: String, onChange: (String) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
        Text("单类证据（不代表买入）", fontSize = 10.sp, color = Muted, fontWeight = FontWeight.SemiBold)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            listOf("B0" to "基础", "B1" to "两融", "B2" to "指数基金", "B3" to "主力").forEach { (key, label) ->
                UniformPoolCell(key, label, value == key, Modifier.weight(1f)) { onChange(key) }
            }
        }
        Text("交叉证据标签", fontSize = 10.sp, color = Muted, fontWeight = FontWeight.SemiBold)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            listOf("B12" to "融+基金", "B13" to "融+主力", "B23" to "基金+主力", "B123" to "三类共同").forEach { (key, label) ->
                UniformPoolCell(key, label, value == key, Modifier.weight(1f)) { onChange(key) }
            }
        }
        TextButton(onClick = { onChange("B4") }, modifier = Modifier.fillMaxWidth()) {
            Text(if (value == "B4") "当前查看：旧 B4 兼容标签" else "查看旧 B4 兼容标签（不作为买入池）", fontSize = 9.sp)
        }
        Text("当前：${poolTitle(value)}", fontSize = 10.sp, color = Blue)
    }
}

@Composable
fun UniformPoolCell(key: String, label: String, selected: Boolean, modifier: Modifier, onClick: () -> Unit) {
    Surface(
        modifier = modifier.height(50.dp).clickable(onClick = onClick),
        color = if (selected) SoftBlue else Color.White,
        shape = RoundedCornerShape(11.dp),
        tonalElevation = if (selected) 1.dp else 0.dp
    ) {
        Column(
            Modifier.fillMaxSize(),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Text(key, fontSize = 10.sp, fontWeight = FontWeight.Bold, color = if (selected) Blue else Ink)
            Text(label, fontSize = 8.sp, color = Muted, maxLines = 1)
        }
    }
}

@Composable
fun Choice(items: List<String>, value: String, onChange: (String) -> Unit) {
    SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
        items.forEachIndexed { index, item ->
            SegmentedButton(
                selected = item == value,
                onClick = { onChange(item) },
                shape = SegmentedButtonDefaults.itemShape(index, items.size),
                label = { Text(displayChoice(item), fontSize = 10.sp) }
            )
        }
    }
}

@Composable
fun CardBlock(content: @Composable ColumnScope.() -> Unit) {
    Card(shape = RoundedCornerShape(16.dp)) {
        Column(Modifier.fillMaxWidth().padding(13.dp), content = content)
    }
}

@Composable
fun Notice(text: String) {
    Surface(color = SoftBlue, shape = RoundedCornerShape(14.dp)) {
        Text(text, modifier = Modifier.fillMaxWidth().padding(11.dp), fontSize = 11.sp, color = Ink)
    }
}

@Composable
fun EmptyCard(text: String) {
    CardBlock { Text(text, color = Muted, fontSize = 12.sp) }
}

@Composable
fun Empty(text: String) {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { Text(text, color = Muted) }
}

@Composable
fun Title(text: String) {
    Text(text, fontSize = 17.sp, fontWeight = FontWeight.Bold)
}

@Composable
fun Key(name: String, value: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
        Text(name, Modifier.weight(1f), fontSize = 10.sp, color = Muted)
        Text(value, fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
    }
}

fun normalizeQuoteTime(raw: String?): String? {
    val v = raw?.trim().orEmpty()
    if (!Regex("\\d{14}").matches(v)) return null
    return runCatching {
        LocalDateTime.parse(v, DateTimeFormatter.ofPattern("yyyyMMddHHmmss"))
            .format(DateTimeFormatter.ofPattern("HH:mm:ss"))
    }.getOrNull()
}

fun zhStatus(v: String?): String = when (v?.lowercase()) {
    "official" -> "正式"
    "preview" -> "预览"
    else -> v ?: "未知"
}

fun breadth(b: Board): Double {
    val total = b.up + b.down + b.flat
    return if (total <= 0) 50.0 else b.up.toDouble() / total.toDouble() * 100.0
}

fun marketOpenNow(): Boolean {
    val now = LocalDateTime.now(CnZone)
    if (now.dayOfWeek == DayOfWeek.SATURDAY || now.dayOfWeek == DayOfWeek.SUNDAY) return false
    val t = now.toLocalTime()
    val morning = !t.isBefore(LocalTime.of(9, 30)) && t.isBefore(LocalTime.of(11, 31))
    val afternoon = !t.isBefore(LocalTime.of(13, 0)) && t.isBefore(LocalTime.of(15, 1))
    return morning || afternoon
}

fun marketStateOk(now: Long, quoteOkAt: Long): Boolean = quoteOkAt > 0 && now - quoteOkAt <= 15000

fun marketStateLabel(now: Long, quoteOkAt: Long, quotes: Map<String, Quote>): String {
    if (quoteOkAt <= 0) return "行情未连接"
    val age = ((now - quoteOkAt).coerceAtLeast(0L) / 1000L)
    if (age > 15) return "行情已过期 ${age}秒"
    val quoteTime = quotes.values.mapNotNull { it.quoteTime }.maxOrNull()
    return if (marketOpenNow()) "行情实时 ${age}秒" else "行情已收盘 ${quoteTime ?: ""}"
}

fun freshnessLabel(now: Long, okAt: Long, staleMs: Long, live: String, stale: String): String {
    if (okAt <= 0) return "未连接"
    val age = ((now - okAt).coerceAtLeast(0L) / 1000L)
    return if (now - okAt <= staleMs) "$live ${age}s" else "$stale ${age}s"
}

fun chinaClock(): String = LocalDateTime.now(CnZone).format(DateTimeFormatter.ofPattern("MM-dd HH:mm:ss"))

fun symbol(code: String): String = when {
    code.startsWith("8") || code.startsWith("9") -> "bj$code"
    code.startsWith("5") || code.startsWith("6") -> "sh$code"
    else -> "sz$code"
}

fun pct(v: Double): String = String.format("%+.2f%%", v)
fun pnl(v: Double): Color = if (v >= 0) Up else Down
fun money(v: Double): String = when {
    abs(v) >= 1e8 -> String.format("%.2f亿", v / 1e8)
    abs(v) >= 1e4 -> String.format("%.1f万", v / 1e4)
    else -> String.format("%.0f", v)
}
fun signedMoney(v: Double): String = (if (v >= 0) "+" else "") + money(v)

fun extractHorizon(p: JSONObject?, h: String): String {
    if (p == null) return "—"
    val direct = p.opt(h)
    if (direct != null && direct != JSONObject.NULL) return pretty(direct)
    val it = p.keys()
    while (it.hasNext()) {
        val k = it.next()
        if (k.equals(h, true) || k.contains(h, true)) return pretty(p.opt(k))
    }
    return "—"
}

fun pretty(v: Any?): String = when (v) {
    null, JSONObject.NULL -> "—"
    is Number -> if (abs(v.toDouble()) < 2.0) String.format("%.2f%%", v.toDouble() * 100.0) else String.format("%.2f", v.toDouble())
    is JSONObject -> {
        val r = v.opt("return")
        if (r != null && r != JSONObject.NULL) pretty(r) else "✓"
    }
    else -> v.toString().take(12)
}


data class TradeAssist(val entry: String, val holding: String, val note: String)


fun tradeAssist(code: String, s: Snapshot, meta: StockMeta?, q: Quote?): TradeAssist {
    val price = q?.price ?: meta?.dayClose ?: meta?.selectionPrice
    val high = q?.high ?: meta?.dayHigh
    val low = q?.low ?: meta?.dayLow
    val chg = q?.change ?: meta?.dayChangePct
    if (price == null || high == null || low == null || low <= 0) {
        return TradeAssist("条件不足，暂不介入", "条件不足，暂不判断离场", "缺少可靠价格区间时不生成交易提示。")
    }
    val nearHigh = high > 0 && price / high >= 0.985
    val nearLow = price / low <= 1.015
    val rangePosition = if (high > low) (price - low) / (high - low) else 0.5
    val entry = when {
        (chg ?: 0.0) >= 8.0 && nearHigh -> "涨幅较大且接近日内高位，不宜追高"
        (chg ?: 0.0) <= -4.0 || nearLow -> "价格处于弱势区，等待重新企稳"
        rangePosition in 0.30..0.68 && (chg ?: 0.0) in -1.5..4.0 -> "价格结构尚可，可观察分批介入"
        rangePosition > 0.80 -> "价格位置偏高，等待回踩确认"
        else -> "保持观察，等待价格结构确认"
    }
    val holding = when {
        (chg ?: 0.0) >= 7.0 && nearHigh -> "已有可卖持仓：接近日内高位，可考虑分批保护利润"
        (chg ?: 0.0) <= -4.0 && nearLow -> "已有可卖持仓：弱势接近日内低位，关注保护性减仓"
        rangePosition >= 0.45 -> "已有可卖持仓：价格结构未明显破坏，可继续观察"
        else -> "已有可卖持仓：暂未触发明确保护条件"
    }
    val today = java.time.LocalDate.now(CnZone).toString()
    val note = if (s.date == today)
        "普通A股当日新买入不可当日卖出；离场提示仅适用于已有可卖持仓。"
    else
        "未录入你的真实成交成本；离场提示目前只依据行情结构。"
    return TradeAssist(entry, holding, note)
}


@Composable
fun TradeAssistStrip(code: String, s: Snapshot, meta: StockMeta?, q: Quote?) {
    val a = tradeAssist(code, s, meta, q)
    Surface(color = Color(0xFFF0F3FA), shape = RoundedCornerShape(10.dp)) {
        Column(Modifier.fillMaxWidth().padding(8.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text("交易辅助", fontSize = 10.sp, fontWeight = FontWeight.Bold)
            Text("介入参考：${a.entry}", fontSize = 9.sp, color = Ink)
            Text("持仓保护：${a.holding}", fontSize = 9.sp, color = Ink)
            Text(a.note, fontSize = 8.sp, color = Muted)
        }
    }
}


fun displayChoice(v: String): String = when (v) {
    "B0" -> "基础强势"
    "B1" -> "两融增强"
    "B2" -> "指数基金申赎"
    "B3" -> "主力资金"
    "B12" -> "两融+指数基金"
    "B13" -> "两融+主力资金"
    "B23" -> "指数基金+主力资金"
    "B123" -> "两融+指数基金+主力资金"
    "B4" -> "旧综合标签（兼容）"
    else -> v
}


fun detailCurrentReturn(perf: JSONObject?): String {
    if (perf == null) return "—"
    val cur = perf.optJSONObject("current")
    val raw = cur?.opt("return")
    if (raw != null && raw != JSONObject.NULL) return pretty(raw)
    for (k in listOf("1D", "5D", "10D", "20D", "60D")) {
        val o = perf.optJSONObject(k) ?: continue
        val r = o.opt("return")
        if (r != null && r != JSONObject.NULL) return pretty(r)
    }
    return "—"
}


@Composable
fun DataCoverageCard(s: Snapshot) {
    val allCodes = s.pools.values.flatten().distinct()
    val metas = allCodes.mapNotNull { s.stocks[it] }
    val priceVerified = metas.count { it.priceProviders.size >= 2 || it.priceMaxRelDiff != null }
    val withOhlc = metas.count { it.dayHigh != null && it.dayLow != null }
    CardBlock {
        Text("数据完整性", fontWeight = FontWeight.Bold)
        Key("入池股票", "${allCodes.size}只")
        Key("价格核对", if (allCodes.isEmpty()) "—" else "$priceVerified/${allCodes.size}")
        Key("当日高低", if (allCodes.isEmpty()) "—" else "$withOhlc/${allCodes.size}")
        Key("主力资金因子", s.factorAvailability["B3"] ?: "未标注")
        if (s.factorAvailability.isNotEmpty()) {
            val missing = s.factorAvailability.filterValues { it.contains("未同步") || it.contains("留空") }
            if (missing.isNotEmpty()) Text(missing.entries.joinToString(" · ") { "${it.key}: ${it.value}" }, fontSize = 8.sp, color = Muted, maxLines = 3)
        }
    }
}


@Composable
fun OfficialSectorRow(x: OfficialSector, date: String) {
    Surface(Modifier.fillMaxWidth().clickable { DetailNav.openSectorName(x.name, date) }, color = Color.White, shape = RoundedCornerShape(16.dp)) {
        Column(Modifier.fillMaxWidth().padding(13.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Row {
                Column(Modifier.weight(1f)) {
                    Text(x.name, fontWeight = FontWeight.Bold)
                    Text("${x.type ?: "板块"} · ${x.status ?: "候选"} · 点开查看并交易", fontSize = 9.sp, color = Muted)
                }
                Text(x.score?.let { String.format("%.1f", it) } ?: "—", fontWeight = FontWeight.Bold, color = Blue)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("涨跌 ${x.changePct?.let(::pct) ?: "—"}", fontSize = 9.sp, color = x.changePct?.let(::pnl) ?: Muted)
                Text("广度 ${x.breadthPct?.let { String.format("%.0f%%", it) } ?: "—"}", fontSize = 9.sp, color = Muted)
            }
            x.reason?.let { Text(it, fontSize = 8.sp, color = Muted, maxLines = 2) }
        }
    }
}


@Composable
fun OfficialMainlineFallback(name: String, date: String) {
    Surface(Modifier.fillMaxWidth().clickable { DetailNav.openSectorName(name, date) }, color = Color.White, shape = RoundedCornerShape(16.dp)) {
        Column(Modifier.fillMaxWidth().padding(13.dp)) {
            Text(name, fontWeight = FontWeight.Bold)
            Text("确认主线 · $date · 点开查看并交易", fontSize = 9.sp, color = Muted)
        }
    }
}


private fun poolDayValuesCompat(s: Snapshot, pool: String): List<Double> = s.pools[pool].orEmpty().mapNotNull { s.stocks[it]?.dayChangePct }

@Composable
fun SameDayPoolCard(s: Snapshot, pool: String) {
    val values = poolDayValuesCompat(s, pool)
    CardBlock {
        Text("信号日行情（不是策略收益）", fontWeight = FontWeight.Bold)
        if (values.isEmpty()) {
            Text("当日涨跌字段尚未同步", color = Muted, fontSize = 11.sp)
        } else {
            val avg = values.average()
            val up = values.count { it > 0 }
            Key("平均涨跌", String.format("%+.2f%%", avg))
            Key("上涨占比", String.format("%.0f%%", up * 100.0 / values.size))
            Key("样本", "${values.size}只")
        }
        Text("这里描述信号形成当天已经发生的行情；真实策略收益从下一交易日可成交价格起算。", fontSize = 8.sp, color = Muted)
    }
}


@Composable
fun ForwardTrackingCard(s: Snapshot, pool: String) {
    val perf = s.poolPerformance[pool]
    CardBlock {
        Text("次一交易日开盘起后续收益跟踪", fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(6.dp))
        if (perf == null || perf.length() == 0) {
            Text(if (s.date == java.time.LocalDate.now(CnZone).toString()) "今日刚冻结：策略收益从下一交易日可成交开盘开始" else "后续收益尚未成熟或尚未同步", color = Muted, fontSize = 11.sp)
        } else {
            TrackingStrip(perf)
        }
        if (!s.performanceEligible) Text("参考跟踪可展示，但不计入策略胜率/超额收益总榜。", fontSize = 8.sp, color = Amber)
    }
}


object DataApi {
    suspend fun fetchPrecomputedPreview(): List<PreviewSector> = withContext(Dispatchers.IO) {
        val root = JSONObject(BackendClient.fetchText("astock_radar/latest.json"))
        val a = root.optJSONArray("mainlines") ?: JSONArray()
        (0 until a.length()).mapNotNull { i ->
            val x = a.optJSONObject(i) ?: return@mapNotNull null
            val name = x.optString("name").takeIf { it.isNotBlank() } ?: return@mapNotNull null
            val board = Board(
                code = x.optString("boardCode"),
                name = name,
                change = num(x, "changePct"),
                amount = num(x, "amount"),
                flow = num(x, "mainNetFlow"),
                flowPct = num(x, "mainFlowPct"),
                up = 0,
                down = 0,
                flat = 0,
                type = if (x.optString("type") == "行业") "industry" else "concept"
            )
            PreviewSector(
                board = board,
                score = num(x, "formationScore") ?: 0.0,
                state = x.optString("stage", "RADAR"),
                momentum = num(x, "accumulationScore") ?: 0.0,
                breadth = num(x, "breadthPct") ?: 0.0,
                flowScore = num(x, "mainFlowPct") ?: 0.0
            )
        }
    }

    suspend fun fetchSnapshots(): List<Snapshot> = withContext(Dispatchers.IO) {
        val a = JSONArray(BackendClient.fetchText("astock_snapshots/index.json"))
        (0 until a.length()).mapNotNull { i -> parseSnapshot(a.optJSONObject(i)) }.sortedBy { it.date }
    }

    suspend fun fetchQuotes(symbols: List<String>): Map<String, Quote> = withContext(Dispatchers.IO) {
        val url = "https://qt.gtimg.cn/q=${symbols.distinct().joinToString(",")}" 
        val text = getBytes(url).toString(Charset.forName("GBK"))
        val out = linkedMapOf<String, Quote>()
        Regex("v_([a-zA-Z0-9]+)=\\\"([^\\\"]*)\\\"").findAll(text).forEach { m ->
            val f = m.groupValues[2].split("~")
            if (f.size > 37) {
                val s = m.groupValues[1]
                out[s] = Quote(
                    symbol = s,
                    name = f.getOrNull(1).orEmpty(),
                    code = f.getOrNull(2).orEmpty(),
                    price = f.getOrNull(3)?.toDoubleOrNull(),
                    prev = f.getOrNull(4)?.toDoubleOrNull(),
                    change = f.getOrNull(32)?.toDoubleOrNull(),
                    high = f.getOrNull(33)?.toDoubleOrNull(),
                    low = f.getOrNull(34)?.toDoubleOrNull(),
                    amount = f.getOrNull(37)?.toDoubleOrNull()?.times(10000.0),
                    quoteTime = normalizeQuoteTime(f.getOrNull(30))
                )
            }
        }
        out
    }

    suspend fun fetchBoards(type: String, delayed: Boolean = false): List<Board> = withContext(Dispatchers.IO) {
        val fs = if (type == "industry") "m:90+t:2+f:!50" else "m:90+t:3+f:!50"
        boardList(fs, type, delayed)
    }

    private fun boardList(fs0: String, type: String, delayed: Boolean = false): List<Board> {
        val fs = URLEncoder.encode(fs0, "UTF-8")
        val host = if (delayed) "push2delay.eastmoney.com" else "push2.eastmoney.com"
        val url = "https://$host/api/qt/clist/get?pn=1&pz=500&po=1&np=1&fltt=2&invt=2&fid=f3&fs=$fs&fields=f3,f6,f12,f14,f62,f184,f104,f105,f106"
        val a = getJson(url).optJSONObject("data")?.optJSONArray("diff") ?: return emptyList()
        return (0 until a.length()).mapNotNull { i ->
            val x = a.optJSONObject(i) ?: return@mapNotNull null
            Board(
                code = x.optString("f12"),
                name = x.optString("f14"),
                change = num(x, "f3"),
                amount = num(x, "f6"),
                flow = num(x, "f62"),
                flowPct = num(x, "f184"),
                up = x.optInt("f104"),
                down = x.optInt("f105"),
                flat = x.optInt("f106"),
                type = type
            )
        }
    }

    private fun parseSnapshot(o: JSONObject?): Snapshot? {
        o ?: return null
        val date = o.optString("date")
        if (date.isBlank()) return null
        val poolsObj = o.optJSONObject("pools") ?: JSONObject()
        val pools = listOf("B0", "B1", "B2", "B3", "B12", "B13", "B23", "B123", "B4")
            .associateWith { key -> arrStrings(poolsObj.optJSONArray(key)) }
            .toMutableMap()
        if (pools["B123"].isNullOrEmpty()) {
            val b2 = pools["B2"].orEmpty().toSet()
            val b3 = pools["B3"].orEmpty().toSet()
            pools["B123"] = pools["B1"].orEmpty().filter { it in b2 && it in b3 }
        }
        val stocks = linkedMapOf<String, StockMeta>()
        val stocksObj = o.optJSONObject("stocks")
        if (stocksObj != null) {
            val it = stocksObj.keys()
            while (it.hasNext()) {
                val code = it.next()
                val x = stocksObj.optJSONObject(code) ?: continue
                val pv = x.optJSONObject("priceValidation")
                stocks[code] = StockMeta(
                    code = code,
                    name = x.optString("name").takeIf { it.isNotBlank() },
                    sector = x.optString("sector").takeIf { it.isNotBlank() },
                    rs = num(x, "RS") ?: num(x, "rs"),
                    mta = x.optString("MTA").takeIf { it.isNotBlank() } ?: x.optString("mta").takeIf { it.isNotBlank() },
                    score = num(x, "score"),
                    reason = x.optString("reason").takeIf { it.isNotBlank() },
                    selectionPrice = num(x, "selectionPrice"),
                    confidence = x.optString("confidence").takeIf { it.isNotBlank() },
                    dayChangePct = num(x, "changePct") ?: num(x, "dayChangePct"),
                    dayOpen = num(x, "dayOpen"),
                    dayClose = num(x, "dayClose") ?: num(x, "selectionPrice"),
                    dayHigh = num(x, "dayHigh"),
                    dayLow = num(x, "dayLow"),
                    dayRangePct = num(x, "dayRangePct"),
                    amount = num(x, "amount"),
                    turnover = num(x, "turnover"),
                    mainNet资金流强度 = num(x, "mainNet资金流强度"),
                    main资金流强度Pct = num(x, "main资金流强度Pct"),
                    rs60 = num(x, "RS60") ?: num(x, "rs60"),
                    priceProviders = arrStrings(pv?.optJSONArray("providers")),
                    priceMaxRelDiff = pv?.let { num(it, "maxRelDiff") }
                )
            }
        }
        val selectedSectors = parseOfficialSectors(o.optJSONArray("selectedSectors"))
        val factorAvailability = stringMap(o.optJSONObject("factorAvailability"))
        val trackingUse = o.optString("trackingUse").takeIf { it.isNotBlank() }
            ?: o.optString("trackingDisplayStatus").takeIf { it.isNotBlank() }
        val audit = o.optJSONObject("audit")
        val auditStatus = audit?.optString("status")?.takeIf { it.isNotBlank() }
        val performanceEligible = audit?.optBoolean("eligibleForPerformanceComparison", auditStatus != "LegacyUnverified") ?: false
        val auditIssues = arrStrings(audit?.optJSONArray("issues"))
        return Snapshot(
            date = date,
            status = o.optString("status", "Unknown"),
            regime = o.optString("regime", "Unknown"),
            strategyVersion = o.optString("strategyVersion").takeIf { it.isNotBlank() },
            auditStatus = auditStatus,
            performanceEligible = performanceEligible,
            auditIssues = auditIssues,
            selectedSectors = selectedSectors,
            factorAvailability = factorAvailability,
            trackingUse = trackingUse,
            mainlines = arrStrings(o.optJSONArray("mainlines")),
            pools = pools,
            stocks = stocks,
            poolPerformance = objMap(o.optJSONObject("poolPerformance") ?: o.optJSONObject("performance")),
            sectorPerformance = objMap(o.optJSONObject("sectorPerformance")),
            stockPerformance = objMap(o.optJSONObject("stockPerformance")),
            note = o.optString("note").takeIf { it.isNotBlank() }
        )
    }

    private fun parseOfficialSectors(a: JSONArray?): List<OfficialSector> {
        if (a == null) return emptyList()
        return (0 until a.length()).mapNotNull { i ->
            val x = a.optJSONObject(i) ?: return@mapNotNull null
            val name = x.optString("name").takeIf { it.isNotBlank() } ?: return@mapNotNull null
            OfficialSector(
                code = x.optString("boardCode", x.optString("code")),
                name = name,
                type = x.optString("type").takeIf { it.isNotBlank() },
                score = num(x, "score"),
                status = x.optString("status").takeIf { it.isNotBlank() },
                changePct = num(x, "changePct"),
                amount = num(x, "amount"),
                mainNet资金流强度 = num(x, "mainNet资金流强度"),
                main资金流强度Pct = num(x, "main资金流强度Pct"),
                breadthPct = num(x, "breadthPct"),
                rs20 = num(x, "RS20"),
                rs60 = num(x, "RS60"),
                mta = x.optString("MTA").takeIf { it.isNotBlank() },
                confidence = x.optString("confidence").takeIf { it.isNotBlank() },
                reason = x.optString("reason").takeIf { it.isNotBlank() }
            )
        }
    }

    private fun stringMap(o: JSONObject?): Map<String, String> {
        if (o == null) return emptyMap()
        val out = linkedMapOf<String, String>()
        val it = o.keys()
        while (it.hasNext()) {
            val k = it.next()
            val v = o.opt(k)
            if (v != null && v != JSONObject.NULL) out[k] = v.toString()
        }
        return out
    }

    private fun arrStrings(a: JSONArray?): List<String> {
        if (a == null) return emptyList()
        return (0 until a.length()).mapNotNull { i -> a.optString(i).takeIf { it.isNotBlank() } }
    }

    private fun objMap(o: JSONObject?): Map<String, JSONObject> {
        if (o == null) return emptyMap()
        val out = linkedMapOf<String, JSONObject>()
        val it = o.keys()
        while (it.hasNext()) {
            val k = it.next()
            o.optJSONObject(k)?.let { out[k] = it }
        }
        return out
    }

    private fun num(o: JSONObject, key: String): Double? {
        val v = o.opt(key)
        return when (v) {
            null, JSONObject.NULL -> null
            is Number -> v.toDouble()
            else -> v.toString().toDoubleOrNull()
        }
    }

    private fun getJson(url: String): JSONObject = JSONObject(getText(url))
    private fun getText(url: String): String = getBytes(url).toString(Charsets.UTF_8)

    private fun getBytes(url: String): ByteArray {
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = 8000
        c.readTimeout = 8000
        c.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 Chrome/140 Mobile Safari/537.36")
        c.setRequestProperty("Accept", "*/*")
        c.setRequestProperty("Cache-Control", "no-cache")
        if (url.contains("gtimg.cn")) c.setRequestProperty("Referer", "https://gu.qq.com/")
        if (url.contains("eastmoney.com")) c.setRequestProperty("Referer", "https://quote.eastmoney.com/")
        c.connect()
        try {
            if (c.responseCode !in 200..299) error("HTTP ${c.responseCode}")
            return c.inputStream.use { it.readBytes() }
        } finally {
            c.disconnect()
        }
    }
}
