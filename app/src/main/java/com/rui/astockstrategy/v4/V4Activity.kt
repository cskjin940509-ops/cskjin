package com.rui.astockstrategy.v4

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
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
import java.text.DecimalFormat
import java.time.LocalDate
import java.time.YearMonth
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.sin

private val Bg = Color(0xFFF6F7FB)
private val Ink = Color(0xFF171A22)
private val Muted = Color(0xFF707788)
private val Blue = Color(0xFF3557D4)
private val Up = Color(0xFFD84343)
private val Down = Color(0xFF15966A)
private val Amber = Color(0xFFAE6A00)

data class Stock(
    val code: String,
    val name: String,
    val line: String,
    val rs: Int,
    val pools: Set<String>,
    val reason: String
)

data class Sector(
    val name: String,
    val rs: Int,
    val breadth: Int,
    val status: String,
    val kind: String = "行业"
)

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
    val time: String?
)

data class Member(
    val code: String,
    val name: String,
    val price: Double?,
    val change: Double?,
    val amount: Double?,
    val flow: Double?
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
    val members: List<Member> = emptyList()
)

data class FundFlow(
    val time: String,
    val main: Double?,
    val large: Double?,
    val superLarge: Double?,
    val mid: Double?,
    val small: Double?
)

data class PoolPerf(
    val d1: Double? = null,
    val d5: Double? = null,
    val d10: Double? = null,
    val d20: Double? = null,
    val d60: Double? = null,
    val alphaWin: Double? = null,
    val medianAlpha: Double? = null
)

data class DailySnapshot(
    val date: String,
    val status: String,
    val regime: String,
    val mainlines: List<String>,
    val pools: Map<String, List<String>>,
    val performance: Map<String, PoolPerf> = emptyMap(),
    val added: List<String> = emptyList(),
    val removed: List<String> = emptyList(),
    val note: String = ""
)

private val stocks = listOf(
    Stock("002371", "北方华创", "半导体设备", 94, setOf("B0", "B1", "B2", "B3", "B4"), "平台型半导体设备龙头，五池共同确认"),
    Stock("688012", "中微公司", "半导体设备", 95, setOf("B0", "B1", "B2", "B3", "B4"), "设备主线核心，五池共同确认"),
    Stock("300308", "中际旭创", "CPO/光模块", 96, setOf("B0", "B1", "B2", "B3", "B4"), "高速光模块核心龙头"),
    Stock("300502", "新易盛", "CPO/光模块", 95, setOf("B0", "B1", "B2", "B3", "B4"), "高速光模块核心龙头"),
    Stock("688008", "澜起科技", "AI芯片/互连", 90, setOf("B0", "B1", "B2", "B3", "B4"), "AI互连与内存接口交叉暴露"),
    Stock("688072", "拓荆科技", "半导体设备", 88, setOf("B0", "B1", "B2", "B4"), "薄膜沉积设备，ETF+两融增强"),
    Stock("002384", "东山精密", "AI PCB", 86, setOf("B0", "B1", "B3", "B4"), "PCB与光通信链交叉"),
    Stock("688361", "中科飞测", "量检测设备", 84, setOf("B0", "B1", "B2", "B4"), "量检测扩散，基本面背离需观察"),
    Stock("300604", "长川科技", "半导体测试", 83, setOf("B3", "B4"), "测试设备扩散"),
    Stock("688981", "中芯国际", "半导体制造", 79, setOf("B1", "B2", "B4"), "融资+ETF确认")
)

private val modelSectors = listOf(
    Sector("半导体设备", 94, 81, "Confirmed", "行业"),
    Sector("CPO/光通信", 92, 76, "Confirmed", "概念"),
    Sector("AI PCB", 87, 72, "Confirmed", "概念"),
    Sector("先进封装", 83, 68, "Candidate", "概念"),
    Sector("机器人", 74, 61, "Candidate", "概念"),
    Sector("创新药", 66, 55, "Rotation", "行业")
)

private val fallbackSnapshots = listOf(
    DailySnapshot(
        date = "2026-08-17",
        status = "Official",
        regime = "震荡上行",
        mainlines = listOf("半导体设备", "CPO/光通信", "AI PCB"),
        pools = mapOf(
            "B0" to listOf("688012", "002371", "688072", "688120", "688361", "300308", "300502", "300394", "300476", "002916"),
            "B1" to listOf("300308", "002371", "300502", "688361", "688012", "300476", "300604", "002384", "688008", "688981"),
            "B2" to listOf("688012", "002371", "300604", "688072", "688120", "688361", "300308", "300502", "300394", "002384"),
            "B3" to listOf("300308", "300502", "688012", "688200", "688008", "002371", "600183", "002384", "688072", "688017"),
            "B4" to listOf("688012", "002371", "300308", "300502", "002384", "688072", "300604", "688361", "688008")
        ),
        note = "正式冻结历史样本；后续表现按可交易口径成熟后回填。"
    ),
    DailySnapshot(
        date = "2026-08-18",
        status = "Preview",
        regime = "震荡上行",
        mainlines = listOf("半导体设备", "CPO/光通信", "AI PCB"),
        pools = mapOf(
            "B0" to listOf("002371", "688012", "300308", "300502", "688072", "002384", "688361", "688008", "002916", "300476"),
            "B1" to listOf("002371", "688012", "300308", "300502", "688072", "002384", "688361", "688008", "688981", "002281"),
            "B2" to listOf("002371", "688012", "300308", "300502", "688072", "688361", "688008", "688120", "688200", "688981"),
            "B3" to listOf("002371", "688012", "300308", "300502", "002384", "688008", "002916", "300476", "300604", "300394"),
            "B4" to listOf("002371", "688012", "300308", "300502", "688008", "688072", "002384", "688361", "300604", "688981")
        ),
        added = listOf("688981"),
        removed = listOf(""),
        note = "盘中预览，不作为正式冻结批次；收盘后 Official 替换。"
    )
)

class V4Activity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { StrategyTerminal() }
    }
}

enum class Tab(val label: String, val icon: ImageVector) {
    HOME("首页", Icons.Default.Home),
    MARKET("行情", Icons.Default.ShowChart),
    MAINLINE("主线", Icons.Default.Radar),
    POOLS("股票池", Icons.Default.ViewList),
    RESEARCH("研究", Icons.Default.Science)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StrategyTerminal() {
    var tab by remember { mutableStateOf(Tab.HOME) }
    var showHistory by remember { mutableStateOf(false) }
    var selectedStock by remember { mutableStateOf<Stock?>(null) }
    var selectedSector by remember { mutableStateOf<Sector?>(null) }
    var quotes by remember { mutableStateOf<Map<String, Quote>>(emptyMap()) }
    var dataStatus by remember { mutableStateOf("连接中") }
    var snapshots by remember { mutableStateOf(fallbackSnapshots) }

    val symbols = remember {
        listOf("sh000001", "sz399006", "sh000688", "sh000300", "sh000852") + stocks.map { marketSymbol(it.code) }
    }

    LaunchedEffect(Unit) {
        runCatching { HistoryApi.fetchSnapshots() }.onSuccess { if (it.isNotEmpty()) snapshots = it }
        while (true) {
            runCatching { MarketData.fetchQuotes(symbols) }
                .onSuccess {
                    if (it.isNotEmpty()) {
                        quotes = it
                        dataStatus = "Live"
                    }
                }
                .onFailure { dataStatus = "Fallback" }
            delay(5000)
        }
    }

    MaterialTheme(colorScheme = lightColorScheme(primary = Blue, background = Bg, surface = Color.White, onSurface = Ink)) {
        Scaffold(
            containerColor = Bg,
            topBar = {
                TopAppBar(
                    title = {
                        Column {
                            Text(if (showHistory) "历史研究看板" else "A股主线研究", fontWeight = FontWeight.Bold)
                            Text(if (showHistory) "Calendar → Snapshot → Performance" else "2026-08-18 · Preview（盘中预览）", fontSize = 11.sp, color = Amber)
                        }
                    },
                    actions = {
                        if (!showHistory) {
                            Text(dataStatus, fontSize = 11.sp, color = if (dataStatus == "Live") Down else Amber)
                        }
                        IconButton(onClick = { showHistory = !showHistory }) {
                            Icon(if (showHistory) Icons.Default.Close else Icons.Default.CalendarMonth, contentDescription = "历史")
                        }
                    }
                )
            },
            bottomBar = {
                NavigationBar {
                    Tab.entries.forEach { item ->
                        NavigationBarItem(
                            selected = !showHistory && tab == item,
                            onClick = { showHistory = false; tab = item },
                            icon = { Icon(item.icon, null) },
                            label = { Text(item.label) }
                        )
                    }
                }
            }
        ) { padding ->
            Box(Modifier.padding(padding).fillMaxSize()) {
                if (showHistory) {
                    HistoryScreen(
                        snapshots = snapshots,
                        onStock = { selectedStock = it },
                        onSector = { selectedSector = it }
                    )
                } else {
                    when (tab) {
                        Tab.HOME -> HomeScreen(quotes, { tab = it }, { selectedStock = it }, { selectedSector = it })
                        Tab.MARKET -> MarketScreen(quotes, { selectedStock = it }, { selectedSector = it })
                        Tab.MAINLINE -> MainlineScreen { selectedSector = it }
                        Tab.POOLS -> PoolsScreen(quotes) { selectedStock = it }
                        Tab.RESEARCH -> ResearchScreen(snapshots)
                    }
                }
            }
        }

        selectedStock?.let { stock ->
            StockDetailDialog(
                stock = stock,
                initialQuote = quotes[marketSymbol(stock.code)],
                snapshots = snapshots,
                onSector = { sector -> selectedStock = null; selectedSector = sector },
                onDismiss = { selectedStock = null }
            )
        }

        selectedSector?.let { sector ->
            SectorDetailDialog(
                sector = sector,
                snapshots = snapshots,
                onStock = { member ->
                    selectedSector = null
                    selectedStock = stocks.firstOrNull { it.code == member.code }
                        ?: Stock(member.code, member.name, sector.name, 0, emptySet(), "板块成分股，当前未进入策略冻结池")
                },
                onDismiss = { selectedSector = null }
            )
        }
    }
}

@Composable
fun HomeScreen(quotes: Map<String, Quote>, go: (Tab) -> Unit, onStock: (Stock) -> Unit, onSector: (Sector) -> Unit) {
    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                MetricCard("Regime", "震荡上行", "模型状态", Modifier.weight(1f))
                MetricCard("主线", "3", "当前重点方向", Modifier.weight(1f))
            }
        }
        item {
            SectionCard {
                Text("公开行情快照", fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(8.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    IndexCell("上证", quotes["sh000001"])
                    IndexCell("创业板", quotes["sz399006"])
                    IndexCell("科创50", quotes["sh000688"])
                }
            }
        }
        item {
            SectionCard {
                Text("市场研究入口", fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    AssistChip(onClick = { go(Tab.MARKET) }, label = { Text("实时热力图") }, leadingIcon = { Icon(Icons.Default.GridView, null) })
                    AssistChip(onClick = { go(Tab.MAINLINE) }, label = { Text("主线雷达") }, leadingIcon = { Icon(Icons.Default.Radar, null) })
                }
            }
        }
        item { SectionTitle("主线地图 · 点击钻取板块") }
        items(modelSectors.take(4)) { SectorRow(it) { onSector(it) } }
        item { SectionTitle("B4 Combined · 点击钻取个股") }
        items(stocks.filter { "B4" in it.pools }.take(6)) { stock ->
            StockRow(stock, quotes[marketSymbol(stock.code)]) { onStock(stock) }
        }
    }
}

@Composable
fun MarketScreen(quotes: Map<String, Quote>, onStock: (Stock) -> Unit, onSector: (Sector) -> Unit) {
    var mode by remember { mutableStateOf("指数") }
    var heatKind by remember { mutableStateOf("行业") }
    var sort by remember { mutableStateOf("涨幅") }
    var boards by remember { mutableStateOf<List<Board>>(emptyList()) }
    var heatStatus by remember { mutableStateOf("未加载") }

    LaunchedEffect(mode, heatKind) {
        if (mode == "热力图") {
            while (true) {
                runCatching { MarketData.fetchBoards(heatKind) }
                    .onSuccess { boards = it; heatStatus = if (it.isNotEmpty()) "Live" else "空" }
                    .onFailure { heatStatus = "接口暂不可用" }
                delay(20_000)
            }
        }
    }

    val sortedBoards = remember(boards, sort) {
        when (sort) {
            "资金" -> boards.sortedByDescending { it.flow ?: Double.NEGATIVE_INFINITY }
            "成交额" -> boards.sortedByDescending { it.amount ?: Double.NEGATIVE_INFINITY }
            else -> boards.sortedByDescending { it.change ?: Double.NEGATIVE_INFINITY }
        }
    }

    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { ChoiceChips(listOf("指数", "热力图", "个股"), mode) { mode = it } }
        when (mode) {
            "指数" -> item {
                SectionCard {
                    Text("公开指数行情", fontWeight = FontWeight.Bold)
                    listOf(
                        "sh000001" to "上证指数",
                        "sz399006" to "创业板指",
                        "sh000688" to "科创50",
                        "sh000300" to "沪深300",
                        "sh000852" to "中证1000"
                    ).forEach { (key, name) -> QuoteLine(name, quotes[key]) }
                }
            }
            "热力图" -> {
                item {
                    SectionCard {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("实时行业 / 概念热力图", fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                            Text(heatStatus, fontSize = 10.sp, color = if (heatStatus == "Live") Down else Amber)
                        }
                        Spacer(Modifier.height(8.dp))
                        ChoiceChips(listOf("行业", "概念"), heatKind) { heatKind = it }
                        Spacer(Modifier.height(6.dp))
                        ChoiceChips(listOf("涨幅", "资金", "成交额"), sort) { sort = it }
                        Text("红=上涨，绿=下跌；点击任意格子进入板块二级详情。", fontSize = 10.sp, color = Muted)
                    }
                }
                if (sortedBoards.isEmpty()) {
                    item { SectionCard { Text("正在读取公开板块行情…", color = Muted) } }
                } else {
                    items(sortedBoards.take(50).chunked(2)) { row ->
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            row.forEach { board ->
                                HeatTile(board, Modifier.weight(1f)) { onSector(boardToSector(board, heatKind)) }
                            }
                            if (row.size == 1) Spacer(Modifier.weight(1f))
                        }
                    }
                }
            }
            else -> items(stocks) { stock -> StockRow(stock, quotes[marketSymbol(stock.code)]) { onStock(stock) } }
        }
    }
}

@Composable
fun HeatTile(board: Board, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val chg = board.change ?: 0.0
    val intensity = (abs(chg) / 6.0).coerceIn(0.10, 1.0).toFloat()
    val base = if (chg >= 0) Up else Down
    Card(
        modifier = modifier.height(106.dp).clickable(onClick = onClick),
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = base.copy(alpha = 0.08f + 0.18f * intensity))
    ) {
        Column(Modifier.fillMaxSize().padding(12.dp), verticalArrangement = Arrangement.SpaceBetween) {
            Text(board.name, fontWeight = FontWeight.Bold, maxLines = 2)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.Bottom) {
                Column {
                    Text(board.change?.let(::formatPct) ?: "—", color = base, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                    Text("↑${board.up}  ↓${board.down}", fontSize = 9.sp, color = Muted)
                }
                Text(board.flow?.let(::formatSignedMoney) ?: "—", fontSize = 9.sp, color = Muted, textAlign = TextAlign.End)
            }
        }
    }
}

@Composable
fun MainlineScreen(onSector: (Sector) -> Unit) {
    var selected by remember { mutableStateOf(modelSectors.first()) }
    var liveBoards by remember { mutableStateOf<List<Board>>(emptyList()) }
    var status by remember { mutableStateOf("读取中") }

    LaunchedEffect(Unit) {
        while (true) {
            runCatching { MarketData.fetchBoards("行业") + MarketData.fetchBoards("概念") }
                .onSuccess { liveBoards = it; status = if (it.isNotEmpty()) "Live" else "Fallback" }
                .onFailure { status = "Fallback" }
            delay(20_000)
        }
    }

    val live = remember(selected, liveBoards) { liveBoards.firstOrNull { boardMatches(selected.name, it.name) } }

    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            SectionCard {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("Mainline Radar（主线雷达）", fontWeight = FontWeight.Bold)
                        Text("模型状态 + 实时板块事实分层展示", color = Muted, fontSize = 11.sp)
                    }
                    Text(status, fontSize = 10.sp, color = if (status == "Live") Down else Amber)
                }
                Spacer(Modifier.height(8.dp))
                MainlineRadar(selected, live)
            }
        }
        item { SectionTitle("主线列表 · 点击切换雷达 / 进入详情") }
        items(modelSectors) { sector ->
            Card(
                Modifier.fillMaxWidth().clickable { selected = sector },
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = if (selected.name == sector.name) Blue.copy(alpha = 0.08f) else Color.White)
            ) {
                Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(sector.name, fontWeight = FontWeight.Bold)
                        Text("${sector.status} · RS ${sector.rs} · Breadth ${sector.breadth}%", fontSize = 11.sp, color = Muted)
                    }
                    TextButton(onClick = { onSector(sector) }) { Text("详情") }
                }
            }
        }
    }
}

@Composable
fun MainlineRadar(sector: Sector, board: Board?) {
    val liveBreadth = board?.let { b -> val t = b.up + b.down + b.flat; if (t > 0) b.up * 100f / t else null }
    val values = listOf(
        sector.rs.toFloat(),
        liveBreadth ?: sector.breadth.toFloat(),
        when (sector.status) { "Confirmed" -> 92f; "Candidate" -> 72f; else -> 52f },
        ((board?.change ?: 0.0) * 7 + 50).coerceIn(0.0, 100.0).toFloat(),
        ((board?.flowPct ?: 0.0) * 4 + 50).coerceIn(0.0, 100.0).toFloat(),
        when (sector.status) { "Confirmed" -> 95f; "Candidate" -> 70f; else -> 50f }
    )
    val labels = listOf("RS", "Breadth", "Trend", "Momentum", "Capital", "Confirm")

    Text("${sector.name} · ${sector.status}", fontWeight = FontWeight.Bold, fontSize = 18.sp)
    Text("实时涨跌 ${board?.change?.let(::formatPct) ?: "—"} · 主力 ${board?.flow?.let(::formatSignedMoney) ?: "—"}", fontSize = 11.sp, color = Muted)
    Spacer(Modifier.height(8.dp))
    Canvas(Modifier.size(220.dp).align(Alignment.CenterHorizontally)) {
        val center = Offset(size.width / 2, size.height / 2)
        val radius = size.minDimension * 0.40f
        repeat(4) { i -> drawCircle(Blue.copy(alpha = 0.10f), radius * (i + 1) / 4f, center, style = Stroke(width = 1f)) }
        val points = values.indices.map { i ->
            val angle = -PI / 2 + 2 * PI * i / values.size
            val edge = Offset((center.x + radius * cos(angle)).toFloat(), (center.y + radius * sin(angle)).toFloat())
            drawLine(Blue.copy(alpha = 0.15f), center, edge, strokeWidth = 1f)
            val r = radius * (values[i] / 100f)
            Offset((center.x + r * cos(angle)).toFloat(), (center.y + r * sin(angle)).toFloat())
        }
        val path = Path()
        points.forEachIndexed { i, p -> if (i == 0) path.moveTo(p.x, p.y) else path.lineTo(p.x, p.y) }
        path.close()
        drawPath(path, Blue.copy(alpha = 0.20f))
        drawPath(path, Blue, style = Stroke(width = 4f))
        points.forEach { drawCircle(Blue, 5f, it) }
    }
    Spacer(Modifier.height(6.dp))
    labels.zip(values).chunked(3).forEach { row ->
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            row.forEach { (label, value) ->
                Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.weight(1f)) {
                    Text(label, fontSize = 9.sp, color = Muted)
                    Text(value.toInt().toString(), fontSize = 12.sp, fontWeight = FontWeight.Bold)
                }
            }
        }
    }
    Text("注：盘中 Momentum / Capital 为 Preview（预览），Official（正式）主线仍按收盘可得数据冻结。", fontSize = 9.sp, color = Amber, modifier = Modifier.padding(top = 8.dp))
}

@Composable
fun PoolsScreen(quotes: Map<String, Quote>, onStock: (Stock) -> Unit) {
    var pool by remember { mutableStateOf("B4") }
    val list = stocks.filter { pool in it.pools }
    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { ChoiceChips(listOf("B0", "B1", "B2", "B3", "B4"), pool) { pool = it } }
        item {
            SectionCard {
                Text(poolName(pool), fontWeight = FontWeight.Bold)
                Text("当前为 8/18 Preview；正式批次收盘后冻结，历史名单不事后改写。", fontSize = 11.sp, color = Amber)
            }
        }
        items(list) { stock -> StockRow(stock, quotes[marketSymbol(stock.code)]) { onStock(stock) } }
    }
}

@Composable
fun ResearchScreen(snapshots: List<DailySnapshot>) {
    val official = snapshots.count { it.status == "Official" }
    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            SectionCard {
                Text("Strategy Scorecard（策略成绩卡）", fontWeight = FontWeight.Bold)
                Text("历史看板中的每日冻结池会自动进入 Forward Tracking（前瞻跟踪）。", color = Muted, fontSize = 11.sp)
                Spacer(Modifier.height(8.dp))
                KeyValue("正式批次", official.toString())
                KeyValue("跟踪周期", "1 / 5 / 10 / 20 / 60D")
            }
        }
        items(listOf("B0 Base", "B1 Margin", "B2 ETF", "B3 Main Flow", "B4 Combined")) { name ->
            SectionCard {
                Row { Text(name, Modifier.weight(1f), fontWeight = FontWeight.SemiBold); Text("Too Early", color = Amber) }
                Text("Alpha Win Rate / Median Alpha / MFE / MAE / Power 随样本成熟回填", fontSize = 10.sp, color = Muted)
            }
        }
    }
}

@Composable
fun HistoryScreen(snapshots: List<DailySnapshot>, onStock: (Stock) -> Unit, onSector: (Sector) -> Unit) {
    var selected by remember { mutableStateOf<DailySnapshot?>(null) }
    if (selected != null) {
        DaySnapshotDetail(selected!!, { selected = null }, onStock, onSector)
        return
    }

    val latest = snapshots.maxByOrNull { it.date }
    var month by remember(latest?.date) { mutableStateOf(latest?.date?.let { YearMonth.from(LocalDate.parse(it)) } ?: YearMonth.now()) }
    val snapMap = snapshots.associateBy { it.date }

    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            SectionCard {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = { month = month.minusMonths(1) }) { Icon(Icons.Default.ChevronLeft, null) }
                    Text("${month.year}年${month.monthValue}月", Modifier.weight(1f), textAlign = TextAlign.Center, fontWeight = FontWeight.Bold)
                    IconButton(onClick = { month = month.plusMonths(1) }) { Icon(Icons.Default.ChevronRight, null) }
                }
                Text("点交易日回看当日市场 → 主线 → B0-B4 → 前瞻表现；历史快照不可回写。", fontSize = 10.sp, color = Muted)
            }
        }
        item { CalendarMonthView(month, snapMap) { selected = it } }
        item { SectionTitle("最近冻结批次") }
        items(snapshots.sortedByDescending { it.date }) { snap ->
            Card(Modifier.fillMaxWidth().clickable { selected = snap }, shape = RoundedCornerShape(16.dp)) {
                Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(snap.date, fontWeight = FontWeight.Bold)
                        Text("${snap.regime} · 主线 ${snap.mainlines.size} · B4 ${snap.pools["B4"].orEmpty().size}", fontSize = 11.sp, color = Muted)
                    }
                    Text(snap.status, color = if (snap.status == "Official") Down else Amber, fontSize = 11.sp)
                }
            }
        }
    }
}

@Composable
fun CalendarMonthView(month: YearMonth, snapshots: Map<String, DailySnapshot>, onSelect: (DailySnapshot) -> Unit) {
    val first = month.atDay(1)
    val offset = first.dayOfWeek.value - 1
    val cells: List<LocalDate?> = List(offset) { null } + (1..month.lengthOfMonth()).map { month.atDay(it) }
    SectionCard {
        Row(Modifier.fillMaxWidth()) {
            listOf("一", "二", "三", "四", "五", "六", "日").forEach { Text(it, Modifier.weight(1f), textAlign = TextAlign.Center, fontSize = 10.sp, color = Muted) }
        }
        Spacer(Modifier.height(6.dp))
        cells.chunked(7).forEach { week ->
            Row(Modifier.fillMaxWidth()) {
                (0 until 7).forEach { idx ->
                    val date = week.getOrNull(idx)
                    val snap = date?.let { snapshots[it.toString()] }
                    val perf = snap?.performance?.get("B4")?.d1
                    Card(
                        modifier = Modifier.weight(1f).aspectRatio(0.86f).padding(2.dp).clickable(enabled = snap != null) { snap?.let(onSelect) },
                        shape = RoundedCornerShape(8.dp),
                        colors = CardDefaults.cardColors(containerColor = if (snap != null) Blue.copy(alpha = 0.06f) else Color.Transparent)
                    ) {
                        Column(Modifier.fillMaxSize().padding(4.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(date?.dayOfMonth?.toString() ?: "", fontSize = 10.sp)
                            if (snap != null) {
                                Text(if (snap.status == "Official") "●" else "○", fontSize = 9.sp, color = if (snap.status == "Official") Down else Amber)
                                Text("B4 ${snap.pools["B4"].orEmpty().size}", fontSize = 7.sp, color = Muted)
                                Text(perf?.let(::formatPct) ?: "未成熟", fontSize = 7.sp, color = perf?.let(::pnlColor) ?: Muted)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun DaySnapshotDetail(snapshot: DailySnapshot, onBack: () -> Unit, onStock: (Stock) -> Unit, onSector: (Sector) -> Unit) {
    var page by remember(snapshot.date) { mutableStateOf("主线") }
    var pool by remember(snapshot.date) { mutableStateOf("B4") }
    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            SectionCard {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = onBack) { Icon(Icons.Default.ArrowBack, null) }
                    Column(Modifier.weight(1f)) {
                        Text(snapshot.date, fontWeight = FontWeight.Bold, fontSize = 18.sp)
                        Text("${snapshot.status} · ${snapshot.regime}", fontSize = 11.sp, color = if (snapshot.status == "Official") Down else Amber)
                    }
                }
                ChoiceChips(listOf("市场", "主线", "股票池", "表现", "变化"), page) { page = it }
            }
        }
        when (page) {
            "市场" -> item {
                SectionCard {
                    Text("当日市场快照", fontWeight = FontWeight.Bold)
                    KeyValue("Regime（市场状态）", snapshot.regime)
                    KeyValue("快照状态", snapshot.status)
                    Text(snapshot.note.ifBlank { "市场行情字段将由日终快照后端持续扩展。" }, fontSize = 10.sp, color = Muted)
                }
            }
            "主线" -> items(snapshot.mainlines) { name ->
                val sector = modelSectors.firstOrNull { boardMatches(it.name, name) || boardMatches(name, it.name) } ?: Sector(name, 0, 0, "Historical")
                SectorRow(sector) { onSector(sector) }
            }
            "股票池" -> {
                item { ChoiceChips(listOf("B0", "B1", "B2", "B3", "B4"), pool) { pool = it } }
                items(snapshot.pools[pool].orEmpty()) { code ->
                    val stock = stockByCode(code)
                    HistoricalStockRow(stock, pool) { onStock(stock) }
                }
            }
            "表现" -> items(listOf("B0", "B1", "B2", "B3", "B4")) { p ->
                PerformanceCard(p, snapshot.performance[p])
            }
            else -> item {
                SectionCard {
                    Text("Diff（相对上一冻结日）", fontWeight = FontWeight.Bold)
                    KeyValue("新增", if (snapshot.added.filter { it.isNotBlank() }.isEmpty()) "—" else snapshot.added.filter { it.isNotBlank() }.joinToString())
                    KeyValue("移除", if (snapshot.removed.filter { it.isNotBlank() }.isEmpty()) "—" else snapshot.removed.filter { it.isNotBlank() }.joinToString())
                    Text("后续会进一步拆分 Upgrade（升级）/ Downgrade（降级）/ Exit（退出）。", fontSize = 10.sp, color = Muted)
                }
            }
        }
    }
}

@Composable
fun PerformanceCard(pool: String, perf: PoolPerf?) {
    SectionCard {
        Row { Text(poolName(pool), Modifier.weight(1f), fontWeight = FontWeight.Bold); Text(if (perf == null) "Too Early" else "Tracking", color = Amber, fontSize = 11.sp) }
        Spacer(Modifier.height(6.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            listOf("1D" to perf?.d1, "5D" to perf?.d5, "10D" to perf?.d10, "20D" to perf?.d20, "60D" to perf?.d60).forEach { (h, v) ->
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(h, fontSize = 9.sp, color = Muted)
                    Text(v?.let(::formatPct) ?: "—", fontSize = 11.sp, color = v?.let(::pnlColor) ?: Muted)
                }
            }
        }
        Spacer(Modifier.height(6.dp))
        KeyValue("Alpha Win Rate", perf?.alphaWin?.let { String.format("%.1f%%", it) } ?: "未成熟")
        KeyValue("Median Alpha", perf?.medianAlpha?.let(::formatPct) ?: "未成熟")
    }
}

@Composable
fun HistoricalStockRow(stock: Stock, pool: String, onClick: () -> Unit) {
    Card(Modifier.fillMaxWidth().clickable(onClick = onClick), shape = RoundedCornerShape(14.dp)) {
        Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(stock.name, fontWeight = FontWeight.Bold)
                Text("${stock.code} · ${stock.line}", fontSize = 10.sp, color = Muted)
            }
            Text(pool, color = Blue, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
fun SectorDetailDialog(sector: Sector, snapshots: List<DailySnapshot>, onStock: (Member) -> Unit, onDismiss: () -> Unit) {
    var board by remember(sector.name) { mutableStateOf<Board?>(null) }
    var page by remember { mutableStateOf("概览") }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(sector.name) {
        runCatching { MarketData.fetchBoard(sector.name) }
            .onSuccess { board = it; if (it == null) error = "公开行情源未精确匹配该板块" }
            .onFailure { error = "板块公开行情暂不可用" }
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = { TextButton(onClick = onDismiss) { Text("关闭") } },
        title = { Column { Text(sector.name); Text(board?.change?.let(::formatPct) ?: "读取公开板块行情…", color = board?.change?.let(::pnlColor) ?: Muted, fontSize = 14.sp) } },
        text = {
            Column {
                ChoiceChips(listOf("概览", "成分", "资金", "策略", "历史"), page) { page = it }
                Spacer(Modifier.height(8.dp))
                LazyColumn(Modifier.heightIn(max = 500.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                    error?.let { item { Text(it, color = Amber, fontSize = 11.sp) } }
                    when (page) {
                        "概览" -> {
                            item { KeyValue("今日涨跌", board?.change?.let(::formatPct) ?: "—") }
                            item { KeyValue("成交额", board?.amount?.let(::formatMoney) ?: "—") }
                            item { KeyValue("上涨 / 下跌 / 平", board?.let { "${it.up} / ${it.down} / ${it.flat}" } ?: "—") }
                            item { KeyValue("模型 RS", if (sector.rs > 0) sector.rs.toString() else "—") }
                            item { KeyValue("模型 Breadth", if (sector.breadth > 0) "${sector.breadth}%" else "—") }
                        }
                        "成分" -> {
                            val members = board?.members.orEmpty()
                            if (members.isEmpty()) item { Text("加载中或暂无公开成分数据", color = Muted) }
                            items(members.take(50)) { member ->
                                Card(Modifier.fillMaxWidth().clickable { onStock(member) }, colors = CardDefaults.cardColors(containerColor = Color(0xFFF8F9FC))) {
                                    Row(Modifier.padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
                                        Column(Modifier.weight(1f)) { Text(member.name, fontWeight = FontWeight.SemiBold); Text(member.code, fontSize = 10.sp, color = Muted) }
                                        Column(horizontalAlignment = Alignment.End) { Text(member.price?.let { DecimalFormat("0.00").format(it) } ?: "—"); Text(member.change?.let(::formatPct) ?: "—", color = member.change?.let(::pnlColor) ?: Muted) }
                                    }
                                }
                            }
                        }
                        "资金" -> {
                            item { KeyValue("主力净流", board?.flow?.let(::formatSignedMoney) ?: "—") }
                            item { KeyValue("主力净流占比", board?.flowPct?.let(::formatPct) ?: "—") }
                            item { Text("主力/大单属于公开成交单分类算法，仍按 C 级因子处理。", fontSize = 10.sp, color = Muted) }
                        }
                        "策略" -> {
                            item { KeyValue("主线状态", sector.status) }
                            item { KeyValue("RS", if (sector.rs > 0) sector.rs.toString() else "Preview") }
                            item { KeyValue("Breadth", if (sector.breadth > 0) "${sector.breadth}%" else "实时计算") }
                            item { Text("实时行情事实与 Official（正式）冻结信号分开保存。", fontSize = 10.sp, color = Muted) }
                        }
                        else -> {
                            val history = snapshots.filter { snap -> snap.mainlines.any { boardMatches(sector.name, it) || boardMatches(it, sector.name) } }
                            if (history.isEmpty()) item { Text("暂无主线确认历史", color = Muted) }
                            items(history.sortedByDescending { it.date }) { snap ->
                                Card(colors = CardDefaults.cardColors(containerColor = Color(0xFFF8F9FC))) {
                                    Row(Modifier.fillMaxWidth().padding(10.dp)) {
                                        Text(snap.date, Modifier.weight(1f), fontWeight = FontWeight.SemiBold)
                                        Text(snap.status, fontSize = 10.sp, color = if (snap.status == "Official") Down else Amber)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    )
}

@Composable
fun StockDetailDialog(stock: Stock, initialQuote: Quote?, snapshots: List<DailySnapshot>, onSector: (Sector) -> Unit, onDismiss: () -> Unit) {
    var quote by remember(stock.code) { mutableStateOf(initialQuote) }
    var flow by remember(stock.code) { mutableStateOf<FundFlow?>(null) }
    var page by remember { mutableStateOf("概览") }

    LaunchedEffect(stock.code) {
        if (quote == null) runCatching { MarketData.fetchQuotes(listOf(marketSymbol(stock.code))) }.onSuccess { quote = it[marketSymbol(stock.code)] }
        runCatching { MarketData.fetchFundFlow(stock.code) }.onSuccess { flow = it }
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = { TextButton(onClick = onDismiss) { Text("关闭") } },
        title = { Column { Text("${stock.name}  ${stock.code}"); Row(verticalAlignment = Alignment.Bottom) { Text(quote?.price?.let { DecimalFormat("0.00").format(it) } ?: "—", fontWeight = FontWeight.Bold, fontSize = 20.sp); Text("  ${quote?.change?.let(::formatPct) ?: ""}", color = quote?.change?.let(::pnlColor) ?: Muted) } } },
        text = {
            Column {
                ChoiceChips(listOf("概览", "趋势", "资金", "策略", "历史", "板块"), page) { page = it }
                Spacer(Modifier.height(8.dp))
                LazyColumn(Modifier.heightIn(max = 490.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                    when (page) {
                        "概览" -> {
                            item { KeyValue("所属主线", stock.line) }
                            item { KeyValue("前收", quote?.prev?.let { DecimalFormat("0.00").format(it) } ?: "—") }
                            item { KeyValue("日高 / 日低", "${quote?.high?.let { DecimalFormat("0.00").format(it) } ?: "—"} / ${quote?.low?.let { DecimalFormat("0.00").format(it) } ?: "—"}") }
                            item { KeyValue("成交额", quote?.amount?.let(::formatMoney) ?: "—") }
                            item { KeyValue("行情时间", quote?.time ?: "—") }
                        }
                        "趋势" -> {
                            item { KeyValue("RS（相对强弱）", if (stock.rs > 0) stock.rs.toString() else "未纳入策略排名") }
                            item { KeyValue("MTA（日/周/月）", if (stock.rs > 0) "D ✓   W ✓   M ✓" else "仅行情观察") }
                            item { Text("K线与 MA20D / MA20W / MA10M 将继续作为下一步图表增强。", fontSize = 10.sp, color = Muted) }
                        }
                        "资金" -> {
                            if (flow == null) item { Text("资金数据加载中或公开接口暂不可用", color = Muted) } else {
                                item { KeyValue("时间", flow!!.time) }
                                item { KeyValue("主力净流", flow!!.main?.let(::formatSignedMoney) ?: "—") }
                                item { KeyValue("超大单", flow!!.superLarge?.let(::formatSignedMoney) ?: "—") }
                                item { KeyValue("大单", flow!!.large?.let(::formatSignedMoney) ?: "—") }
                                item { KeyValue("中单", flow!!.mid?.let(::formatSignedMoney) ?: "—") }
                                item { KeyValue("小单", flow!!.small?.let(::formatSignedMoney) ?: "—") }
                            }
                            item { Text("主力/大单为 C 级算法分类；两融正式信号按披露时点进入快照。", fontSize = 10.sp, color = Muted) }
                        }
                        "策略" -> {
                            item { KeyValue("出现池", if (stock.pools.isEmpty()) "未入当前池" else stock.pools.sorted().joinToString(" / ")) }
                            item { KeyValue("状态", if (stock.pools.isEmpty()) "Market" else "Active") }
                            item { Text("入池逻辑", fontWeight = FontWeight.Bold) }
                            item { Text(stock.reason, fontSize = 12.sp, color = Muted) }
                        }
                        "历史" -> {
                            val timeline = snapshots.mapNotNull { snap ->
                                val pools = snap.pools.filterValues { stock.code in it }.keys.sorted()
                                if (pools.isEmpty()) null else snap to pools
                            }.sortedByDescending { it.first.date }
                            if (timeline.isEmpty()) item { Text("暂无冻结池历史", color = Muted) }
                            items(timeline) { (snap, pools) ->
                                Card(colors = CardDefaults.cardColors(containerColor = Color(0xFFF8F9FC))) {
                                    Row(Modifier.fillMaxWidth().padding(10.dp)) {
                                        Column(Modifier.weight(1f)) { Text(snap.date, fontWeight = FontWeight.SemiBold); Text(pools.joinToString(" / "), fontSize = 10.sp, color = Blue) }
                                        Text(snap.status, fontSize = 10.sp, color = if (snap.status == "Official") Down else Amber)
                                    }
                                }
                            }
                        }
                        else -> {
                            val related = relatedSectors(stock)
                            items(related) { sector ->
                                Card(Modifier.fillMaxWidth().clickable { onSector(sector) }, colors = CardDefaults.cardColors(containerColor = Color(0xFFF8F9FC))) {
                                    Row(Modifier.padding(10.dp)) { Text(sector.name, Modifier.weight(1f), fontWeight = FontWeight.SemiBold); Text("进入板块", color = Blue, fontSize = 10.sp) }
                                }
                            }
                        }
                    }
                }
            }
        }
    )
}

@Composable
fun MetricCard(title: String, value: String, subtitle: String, modifier: Modifier = Modifier) {
    Card(modifier, shape = RoundedCornerShape(16.dp)) {
        Column(Modifier.padding(14.dp)) { Text(title, fontSize = 11.sp, color = Muted); Text(value, fontWeight = FontWeight.Bold, fontSize = 19.sp); Text(subtitle, fontSize = 10.sp, color = Muted) }
    }
}

@Composable
fun SectionCard(content: @Composable ColumnScope.() -> Unit) {
    Card(shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.fillMaxWidth().padding(14.dp), content = content)
    }
}

@Composable fun SectionTitle(text: String) = Text(text, fontWeight = FontWeight.Bold, fontSize = 17.sp)

@Composable
fun IndexCell(name: String, quote: Quote?) {
    Column { Text(name, fontSize = 11.sp, color = Muted); Text(quote?.price?.let { DecimalFormat("0.00").format(it) } ?: "—", fontWeight = FontWeight.Bold); Text(quote?.change?.let(::formatPct) ?: "—", color = quote?.change?.let(::pnlColor) ?: Muted, fontSize = 11.sp) }
}

@Composable
fun QuoteLine(name: String, quote: Quote?) {
    Row(Modifier.fillMaxWidth().padding(vertical = 7.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(name, Modifier.weight(1f)); Text(quote?.price?.let { DecimalFormat("0.00").format(it) } ?: "—", fontWeight = FontWeight.SemiBold); Spacer(Modifier.width(12.dp)); Text(quote?.change?.let(::formatPct) ?: "—", color = quote?.change?.let(::pnlColor) ?: Muted)
    }
}

@Composable
fun SectorRow(sector: Sector, onClick: () -> Unit) {
    Card(Modifier.fillMaxWidth().clickable(onClick = onClick), shape = RoundedCornerShape(16.dp)) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) { Text(sector.name, fontWeight = FontWeight.Bold); Text("${sector.status} · ${sector.kind} · Breadth ${if (sector.breadth > 0) "${sector.breadth}%" else "—"}", fontSize = 11.sp, color = Muted) }
            Text(if (sector.rs > 0) "RS ${sector.rs}" else "Preview", color = Blue, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
fun StockRow(stock: Stock, quote: Quote?, onClick: () -> Unit) {
    Card(Modifier.fillMaxWidth().clickable(onClick = onClick), shape = RoundedCornerShape(16.dp)) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) { Text(stock.name, fontWeight = FontWeight.Bold); Text("${stock.code} · ${stock.line}", fontSize = 11.sp, color = Muted); Text(stock.pools.sorted().joinToString(" "), fontSize = 10.sp, color = Blue) }
            Column(horizontalAlignment = Alignment.End) { Text(quote?.price?.let { DecimalFormat("0.00").format(it) } ?: "—", fontWeight = FontWeight.Bold); Text(quote?.change?.let(::formatPct) ?: "—", color = quote?.change?.let(::pnlColor) ?: Muted, fontSize = 11.sp); if (stock.rs > 0) Text("RS ${stock.rs}", fontSize = 10.sp, color = Blue) }
        }
    }
}

@Composable
fun ChoiceChips(values: List<String>, selected: String, onSelect: (String) -> Unit) {
    LazyRow(horizontalArrangement = Arrangement.spacedBy(7.dp)) {
        items(values) { value -> FilterChip(selected = value == selected, onClick = { onSelect(value) }, label = { Text(value) }) }
    }
}

@Composable
fun KeyValue(key: String, value: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { Text(key, fontSize = 12.sp, color = Muted); Spacer(Modifier.width(12.dp)); Text(value, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.End) }
}

object MarketData {
    suspend fun fetchQuotes(symbols: List<String>): Map<String, Quote> = withContext(Dispatchers.IO) {
        val connection = (URL("https://qt.gtimg.cn/q=${symbols.distinct().joinToString(",")}").openConnection() as HttpURLConnection).apply {
            connectTimeout = 7000; readTimeout = 7000; setRequestProperty("User-Agent", "Mozilla/5.0 Android AStockStrategy")
        }
        try {
            val text = connection.inputStream.use { it.readBytes() }.toString(Charset.forName("GBK"))
            val output = linkedMapOf<String, Quote>()
            val regex = Regex("v_([a-zA-Z0-9]+)=\\\"([^\\\"]*)\\\"")
            regex.findAll(text).forEach { match ->
                val fields = match.groupValues[2].split("~")
                if (fields.size > 37) {
                    val symbol = match.groupValues[1]
                    output[symbol] = Quote(symbol, fields.getOrNull(1).orEmpty(), fields.getOrNull(2).orEmpty(), fields.getOrNull(3)?.toDoubleOrNull(), fields.getOrNull(4)?.toDoubleOrNull(), fields.getOrNull(32)?.toDoubleOrNull(), fields.getOrNull(33)?.toDoubleOrNull(), fields.getOrNull(34)?.toDoubleOrNull(), fields.getOrNull(37)?.toDoubleOrNull()?.times(10_000), fields.getOrNull(30))
                }
            }
            output
        } finally { connection.disconnect() }
    }

    suspend fun fetchBoards(kind: String): List<Board> = withContext(Dispatchers.IO) {
        boardList(if (kind == "行业") "m:90+t:2+f:!50" else "m:90+t:3+f:!50")
    }

    suspend fun fetchBoard(name: String): Board? = withContext(Dispatchers.IO) {
        val candidates = boardList("m:90+t:2+f:!50") + boardList("m:90+t:3+f:!50")
        val found = candidates.firstOrNull { it.name == name }
            ?: candidates.firstOrNull { boardMatches(name, it.name) }
            ?: return@withContext null
        found.copy(members = members(found.code))
    }

    suspend fun fetchFundFlow(code: String): FundFlow? = withContext(Dispatchers.IO) {
        val market = if (code.startsWith("6") || code.startsWith("5") || code.startsWith("9")) "1" else "0"
        val url = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get?secid=$market.$code&klt=1&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57"
        val klines = getJson(url).optJSONObject("data")?.optJSONArray("klines") ?: return@withContext null
        if (klines.length() == 0) return@withContext null
        val parts = klines.optString(klines.length() - 1).split(",")
        FundFlow(parts.getOrNull(0).orEmpty(), parts.getOrNull(1)?.toDoubleOrNull(), parts.getOrNull(4)?.toDoubleOrNull(), parts.getOrNull(5)?.toDoubleOrNull(), parts.getOrNull(3)?.toDoubleOrNull(), parts.getOrNull(2)?.toDoubleOrNull())
    }

    private fun boardList(fs: String): List<Board> {
        val url = "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=500&po=1&np=1&fltt=2&invt=2&fid=f3&fs=${URLEncoder.encode(fs, "UTF-8")}&fields=f3,f6,f12,f14,f62,f184,f104,f105,f106"
        val array = getJson(url).optJSONObject("data")?.optJSONArray("diff") ?: return emptyList()
        return buildList {
            for (i in 0 until array.length()) {
                val item = array.optJSONObject(i) ?: continue
                add(Board(item.optString("f12"), item.optString("f14"), number(item, "f3"), number(item, "f6"), number(item, "f62"), number(item, "f184"), item.optInt("f104"), item.optInt("f105"), item.optInt("f106")))
            }
        }
    }

    private fun members(boardCode: String): List<Member> {
        val fs = URLEncoder.encode("b:$boardCode", "UTF-8")
        val url = "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=100&po=1&np=1&fltt=2&invt=2&fid=f3&fs=$fs&fields=f2,f3,f6,f12,f14,f62"
        val array = getJson(url).optJSONObject("data")?.optJSONArray("diff") ?: return emptyList()
        return buildList {
            for (i in 0 until array.length()) {
                val item = array.optJSONObject(i) ?: continue
                add(Member(item.optString("f12"), item.optString("f14"), number(item, "f2"), number(item, "f3"), number(item, "f6"), number(item, "f62")))
            }
        }
    }

    private fun getJson(url: String): JSONObject {
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 8000; readTimeout = 10000; setRequestProperty("User-Agent", "Mozilla/5.0 Android AStockStrategy"); setRequestProperty("Referer", "https://quote.eastmoney.com/")
        }
        return try { JSONObject(connection.inputStream.bufferedReader().use { it.readText() }) } finally { connection.disconnect() }
    }

    private fun number(json: JSONObject, key: String): Double? {
        if (!json.has(key) || json.isNull(key)) return null
        val value = json.optDouble(key, Double.NaN)
        return if (value.isNaN()) null else value
    }
}

object HistoryApi {
    suspend fun fetchSnapshots(): List<DailySnapshot> = withContext(Dispatchers.IO) {
        val url = "https://raw.githubusercontent.com/cskjin940509-ops/cskjin/main/astock_snapshots/index.json"
        val conn = (URL(url).openConnection() as HttpURLConnection).apply { connectTimeout = 6000; readTimeout = 6000; setRequestProperty("User-Agent", "AStockStrategy/0.4") }
        try {
            val text = conn.inputStream.bufferedReader().use { it.readText() }
            parseSnapshots(JSONArray(text)).ifEmpty { fallbackSnapshots }
        } catch (_: Exception) { fallbackSnapshots } finally { conn.disconnect() }
    }

    private fun parseSnapshots(array: JSONArray): List<DailySnapshot> = buildList {
        for (i in 0 until array.length()) {
            val o = array.optJSONObject(i) ?: continue
            val poolsObj = o.optJSONObject("pools") ?: JSONObject()
            val pools = listOf("B0", "B1", "B2", "B3", "B4").associateWith { key -> jsonStrings(poolsObj.optJSONArray(key)) }
            val perfObj = o.optJSONObject("performance")
            val perf = buildMap {
                if (perfObj != null) listOf("B0", "B1", "B2", "B3", "B4").forEach { key ->
                    perfObj.optJSONObject(key)?.let { p -> put(key, PoolPerf(numberOrNull(p, "d1"), numberOrNull(p, "d5"), numberOrNull(p, "d10"), numberOrNull(p, "d20"), numberOrNull(p, "d60"), numberOrNull(p, "alphaWin"), numberOrNull(p, "medianAlpha"))) }
                }
            }
            add(DailySnapshot(o.optString("date"), o.optString("status", "Official"), o.optString("regime", "Unknown"), jsonStrings(o.optJSONArray("mainlines")), pools, perf, jsonStrings(o.optJSONArray("added")), jsonStrings(o.optJSONArray("removed")), o.optString("note")))
        }
    }

    private fun jsonStrings(a: JSONArray?): List<String> = if (a == null) emptyList() else (0 until a.length()).map { a.optString(it) }.filter { it.isNotBlank() }
    private fun numberOrNull(o: JSONObject, k: String): Double? = if (!o.has(k) || o.isNull(k)) null else o.optDouble(k).takeUnless { it.isNaN() }
}

private fun marketSymbol(code: String): String = if (code.startsWith("6") || code.startsWith("5") || code.startsWith("9")) "sh$code" else "sz$code"
private fun formatPct(value: Double): String = (if (value >= 0) "+" else "") + String.format("%.2f%%", value)
private fun pnlColor(value: Double): Color = if (value >= 0) Up else Down
private fun formatMoney(value: Double): String = when { abs(value) >= 1e12 -> String.format("%.2f万亿", value / 1e12); abs(value) >= 1e8 -> String.format("%.2f亿", value / 1e8); abs(value) >= 1e4 -> String.format("%.1f万", value / 1e4); else -> DecimalFormat("#,##0").format(value) }
private fun formatSignedMoney(value: Double): String = (if (value < 0) "-" else "+") + formatMoney(abs(value))
private fun poolName(pool: String): String = when (pool) { "B0" -> "B0 Base（基础池）"; "B1" -> "B1 Margin（两融增强）"; "B2" -> "B2 ETF（ETF增强）"; "B3" -> "B3 Main Flow（主力增强）"; else -> "B4 Combined（联合池）" }

private fun stockByCode(code: String): Stock = stocks.firstOrNull { it.code == code } ?: Stock(code, code, "历史候选", 0, emptySet(), "历史冻结批次中的股票")

private fun boardToSector(board: Board, kind: String): Sector {
    val known = modelSectors.firstOrNull { boardMatches(it.name, board.name) }
    if (known != null) return known
    val total = board.up + board.down + board.flat
    val breadth = if (total > 0) board.up * 100 / total else 50
    val score = (50 + (board.change ?: 0.0) * 6 + (board.flowPct ?: 0.0) * 2 + (breadth - 50) * 0.25).coerceIn(0.0, 100.0).toInt()
    val status = when { score >= 80 -> "Preview Strong"; score >= 65 -> "Preview Watch"; else -> "Market" }
    return Sector(board.name, score, breadth, status, kind)
}

private fun boardMatches(model: String, board: String): Boolean {
    if (model == board || model.contains(board) || board.contains(model)) return true
    val clean = model.replace("AI ", "").replace("AI", "")
    val tokens = clean.split("/", "、", "+", " ").map { it.trim() }.filter { it.length >= 2 }
    return tokens.any { board.contains(it) || it.contains(board) }
}

private fun relatedSectors(stock: Stock): List<Sector> {
    val names = when {
        stock.line.contains("CPO") || stock.line.contains("光") -> listOf("CPO/光通信")
        stock.line.contains("PCB") -> listOf("AI PCB", "CPO/光通信")
        stock.line.contains("半导体") || stock.line.contains("量检测") -> listOf("半导体设备", "先进封装")
        else -> listOf(stock.line)
    }
    return names.distinct().map { name -> modelSectors.firstOrNull { it.name == name } ?: Sector(name, 0, 0, "Related") }
}
