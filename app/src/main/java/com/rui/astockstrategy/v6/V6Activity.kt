package com.rui.astockstrategy.v6

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
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
import androidx.compose.material.icons.filled.Radar
import androidx.compose.material.icons.filled.ViewList
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
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

data class StockMeta(
    val code: String,
    val name: String?,
    val sector: String?,
    val rs: Double?,
    val mta: String?,
    val score: Double?,
    val reason: String?,
    val selectionPrice: Double?,
    val confidence: String?
)

data class Snapshot(
    val date: String,
    val status: String,
    val regime: String,
    val strategyVersion: String?,
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

class V6Activity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { AStockV6() }
    }
}

enum class Tab(val label: String, val icon: ImageVector) {
    TODAY("今日", Icons.Default.Home),
    MARKET("行情", Icons.Default.GridView),
    MAINLINE("主线", Icons.Default.Radar),
    POOLS("股票池", Icons.Default.ViewList),
    HISTORY("历史", Icons.Default.CalendarMonth)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AStockV6() {
    var tab by remember { mutableStateOf(Tab.TODAY) }
    var snapshots by remember { mutableStateOf<List<Snapshot>>(emptyList()) }
    var selectedDate by remember { mutableStateOf<String?>(null) }
    var quotes by remember { mutableStateOf<Map<String, Quote>>(emptyMap()) }
    var industries by remember { mutableStateOf<List<Board>>(emptyList()) }
    var concepts by remember { mutableStateOf<List<Board>>(emptyList()) }
    var quoteOkAt by remember { mutableLongStateOf(0L) }
    var boardOkAt by remember { mutableLongStateOf(0L) }
    var snapshotOkAt by remember { mutableLongStateOf(0L) }
    var tick by remember { mutableLongStateOf(System.currentTimeMillis()) }
    var quoteError by remember { mutableStateOf<String?>(null) }
    var boardError by remember { mutableStateOf<String?>(null) }

    val latest = snapshots.maxByOrNull { it.date }
    val active = selectedDate?.let { date -> snapshots.firstOrNull { it.date == date } } ?: latest
    val activeCodes = active?.pools?.values?.flatten()?.distinct().orEmpty()
    val preview = remember(industries, concepts) { makePreview((industries + concepts).distinctBy { it.code }) }

    LaunchedEffect(Unit) {
        while (true) {
            tick = System.currentTimeMillis()
            delay(1000)
        }
    }

    LaunchedEffect(Unit) {
        while (true) {
            runCatching { DataApi.fetchSnapshots() }
                .onSuccess {
                    if (it.isNotEmpty()) snapshots = it
                    snapshotOkAt = System.currentTimeMillis()
                }
            runCatching {
                val ind = DataApi.fetchBoards("industry")
                val con = DataApi.fetchBoards("concept")
                ind to con
            }.onSuccess { pair ->
                industries = pair.first
                concepts = pair.second
                boardOkAt = System.currentTimeMillis()
                boardError = null
            }.onFailure {
                boardError = it.javaClass.simpleName
            }
            delay(30000)
        }
    }

    LaunchedEffect(activeCodes.joinToString(",")) {
        while (true) {
            val symbols = (listOf("sh000001", "sz399006", "sh000688", "sh000300", "sh000852") + activeCodes.map(::symbol)).distinct()
            if (symbols.isNotEmpty()) {
                runCatching { DataApi.fetchQuotes(symbols) }
                    .onSuccess {
                        if (it.isNotEmpty()) {
                            quotes = it
                            quoteOkAt = System.currentTimeMillis()
                            quoteError = null
                        }
                    }
                    .onFailure { quoteError = it.javaClass.simpleName }
            }
            delay(5000)
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
                            Text("A股主线研究", fontWeight = FontWeight.Bold)
                            Text(
                                active?.let { "${it.date} · ${it.status} · ${it.regime}" } ?: "等待策略快照",
                                fontSize = 11.sp,
                                color = if (active?.status == "Official") Down else Amber
                            )
                        }
                    },
                    actions = {
                        LivePill(label = marketStateLabel(tick, quoteOkAt, quotes), ok = marketStateOk(tick, quoteOkAt))
                        Spacer(Modifier.width(8.dp))
                    }
                )
            },
            bottomBar = {
                NavigationBar {
                    Tab.entries.forEach { item ->
                        NavigationBarItem(
                            selected = tab == item,
                            onClick = {
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
                when (tab) {
                    Tab.TODAY -> TodayScreen(active, preview, quotes, tick, quoteOkAt, boardOkAt)
                    Tab.MARKET -> MarketScreen(quotes, industries, concepts, tick, quoteOkAt, boardOkAt, quoteError, boardError)
                    Tab.MAINLINE -> MainlineScreen(active, preview, tick, boardOkAt)
                    Tab.POOLS -> PoolsScreen(active, quotes, tick, quoteOkAt)
                    Tab.HISTORY -> HistoryScreen(snapshots, active, quotes, selectedDate) { selectedDate = it }
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
    boardOkAt: Long
) {
    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            StatusCard(now, quoteOkAt, boardOkAt, s)
        }
        item { Title("Intraday Preview（盘中预览）") }
        item {
            Notice("盘中只用当前可实时取得的公开行情生成主线候选，不冒充正式 B1/B2/B3/B4。正式 Daily Cohort 收盘后另行冻结。")
        }
        if (preview.isEmpty()) {
            item { EmptyCard("实时板块数据暂不可用") }
        } else {
            items(preview.take(5)) { p -> PreviewRow(p) }
        }
        item { Title("Latest Official / Snapshot") }
        if (s == null) {
            item { EmptyCard("尚未读取到正式策略快照") }
        } else {
            item {
                CardBlock {
                    Key("日期", s.date)
                    Key("状态", s.status)
                    Key("Regime", s.regime)
                    Key("主线", s.mainlines.joinToString(" / ").ifBlank { "—" })
                    Key("B4", "${s.pools["B4"].orEmpty().size}只")
                }
            }
            val b4 = s.pools["B4"].orEmpty()
            if (b4.isNotEmpty()) {
                item { Title("B4 Live Monitor（实时跟踪）") }
                items(b4.take(8)) { code -> StockLiveRow(code, s, quotes[symbol(code)]) }
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
                    Text("Data Status（数据状态）", fontWeight = FontWeight.Bold)
                    Text("实时行情和策略快照分开显示", fontSize = 10.sp, color = Muted)
                }
                Text(chinaClock(), fontSize = 12.sp, fontWeight = FontWeight.Bold)
            }
            Spacer(Modifier.height(10.dp))
            Key("个股/指数", marketStateLabel(now, quoteOkAt, emptyMap()))
            Key("行业/概念", freshnessLabel(now, boardOkAt, 70000, "LIVE", "STALE"))
            Key("正式策略", s?.let { "${it.date} ${it.status}" } ?: "未同步")
            Key("盘中主线", if (marketOpenNow()) "LIVE Preview" else "Close Preview")
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
                LiveBadge("行情", freshnessLabel(now, quoteOkAt, 15000, "LIVE", "STALE"), marketStateOk(now, quoteOkAt), Modifier.weight(1f))
                LiveBadge("板块", freshnessLabel(now, boardOkAt, 70000, "LIVE", "STALE"), now - boardOkAt <= 70000, Modifier.weight(1f))
            }
        }
        if (quoteError != null || boardError != null) {
            item { Notice("请求异常：行情 ${quoteError ?: "OK"}；板块 ${boardError ?: "OK"}。页面会明确标记 stale，不再把旧值伪装成 Live。") }
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
        item { Title("实时${type}热力图") }
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
    var mode by remember { mutableStateOf("盘中Preview") }
    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { Choice(listOf("盘中Preview", "Official"), mode) { mode = it } }
        if (mode == "盘中Preview") {
            item {
                Notice("实时主线候选每30秒随公开行业/概念行情重新计算；这是 Preview，不写入历史，不代表收盘后的正式主线。")
            }
            item {
                LiveBadge("Mainline Preview", freshnessLabel(now, boardOkAt, 70000, "LIVE", "STALE"), now - boardOkAt <= 70000, Modifier.fillMaxWidth())
            }
            if (preview.isEmpty()) {
                item { EmptyCard("等待实时板块数据") }
            } else {
                items(preview.take(12)) { PreviewRadar(it) }
            }
        } else {
            if (s == null) {
                item { EmptyCard("暂无 Official Snapshot") }
            } else {
                item { Notice("${s.date} ${s.status}：这一页只显示当日冻结结果，不会随今天行情改写。") }
                if (s.mainlines.isEmpty()) item { EmptyCard("该日无主线") }
                items(s.mainlines) { name ->
                    CardBlock {
                        Text(name, fontWeight = FontWeight.Bold)
                        Text("冻结于 ${s.date}", fontSize = 10.sp, color = Muted)
                    }
                }
            }
        }
    }
}

@Composable
fun PoolsScreen(s: Snapshot?, quotes: Map<String, Quote>, now: Long, quoteOkAt: Long) {
    if (s == null) {
        Empty("暂无正式股票池快照")
        return
    }
    var pool by remember(s.date) { mutableStateOf("B4") }
    val codes = s.pools[pool].orEmpty()
    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
        item { Choice(listOf("B0", "B1", "B2", "B3", "B4"), pool) { pool = it } }
        item {
            Notice("$pool 名单来自 ${s.date} 的 ${s.status} Daily Cohort；股票价格是 Live Monitor。名单本身不会盘中乱跳。")
        }
        item {
            LiveBadge("Pool Quotes", freshnessLabel(now, quoteOkAt, 15000, "LIVE", "STALE"), marketStateOk(now, quoteOkAt), Modifier.fillMaxWidth())
        }
        if (codes.isEmpty()) {
            item { EmptyCard("该日 $pool 没有达标股票") }
        } else {
            items(codes) { code -> StockLiveRow(code, s, quotes[symbol(code)]) }
        }
        item { PerformanceCard("$pool 后续表现", s.poolPerformance[pool]) }
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
    if (all.isEmpty()) {
        Empty("历史数据库为空")
        return
    }
    val sorted = all.sortedByDescending { it.date }
    var pool by remember(s?.date) { mutableStateOf("B4") }
    val snap = s ?: sorted.first()
    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { Title("Time Machine（历史时间机器）") }
        item { Notice("点任意交易日，查看那一天真实筛出的板块/股票，以及这批对象后续的收益。原名单冻结，只更新 Tracking。") }
        items(sorted.take(40).chunked(4)) { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                row.forEach { item -> DateChip(item, selectedDate == item.date || (selectedDate == null && item.date == snap.date), Modifier.weight(1f)) { onDate(item.date) } }
                repeat(4 - row.size) { Spacer(Modifier.weight(1f)) }
            }
        }
        item { CardBlock { Key("日期", snap.date); Key("状态", snap.status); Key("Regime", snap.regime); Key("主线", snap.mainlines.joinToString(" / ").ifBlank { "—" }) } }
        item { Choice(listOf("B0", "B1", "B2", "B3", "B4"), pool) { pool = it } }
        val codes = snap.pools[pool].orEmpty()
        if (codes.isEmpty()) item { EmptyCard("当日 $pool 为空") }
        items(codes) { code -> HistoryStockRow(code, snap, quotes[symbol(code)]) }
        item { PerformanceCard("$pool Cohort Forward Tracking", snap.poolPerformance[pool]) }
        snap.note?.let { item { Notice(it) } }
    }
}

@Composable
fun PreviewRow(p: PreviewSector) {
    Card(shape = RoundedCornerShape(16.dp)) {
        Column(Modifier.padding(13.dp)) {
            Row {
                Column(Modifier.weight(1f)) {
                    Text(p.board.name, fontWeight = FontWeight.Bold)
                    Text("${p.board.type} · ${p.state}", fontSize = 10.sp, color = Blue)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(p.board.change?.let(::pct) ?: "—", color = p.board.change?.let(::pnl) ?: Muted, fontWeight = FontWeight.Bold)
                    Text("Score ${String.format("%.0f", p.score)}", fontSize = 10.sp, color = Muted)
                }
            }
            Spacer(Modifier.height(8.dp))
            ProgressLine("Momentum", p.momentum)
            ProgressLine("Breadth", p.breadth)
            ProgressLine("Flow", p.flowScore)
        }
    }
}

@Composable
fun PreviewRadar(p: PreviewSector) {
    Card(shape = RoundedCornerShape(16.dp)) {
        Column(Modifier.padding(14.dp)) {
            Row {
                Column(Modifier.weight(1f)) {
                    Text(p.board.name, fontWeight = FontWeight.Bold)
                    Text(p.state, color = if (p.state == "Confirmed Candidate") Down else Amber, fontSize = 10.sp)
                }
                Text("${String.format("%.0f", p.score)}", fontSize = 20.sp, fontWeight = FontWeight.Bold)
            }
            Spacer(Modifier.height(8.dp))
            ProgressLine("Momentum", p.momentum)
            ProgressLine("Breadth", p.breadth)
            ProgressLine("Flow", p.flowScore)
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
    Card(shape = RoundedCornerShape(15.dp)) {
        Column(Modifier.padding(12.dp)) {
            Row {
                Column(Modifier.weight(1f)) {
                    Text(meta?.name ?: q?.name ?: code, fontWeight = FontWeight.Bold)
                    Text("$code · ${meta?.sector ?: "—"}", fontSize = 10.sp, color = Muted)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(q?.price?.let { String.format("%.2f", it) } ?: "—", fontWeight = FontWeight.Bold)
                    Text(q?.change?.let(::pct) ?: "—", color = q?.change?.let(::pnl) ?: Muted, fontSize = 11.sp)
                }
            }
            val selection = meta?.selectionPrice
            val liveReturn = if (selection != null && selection > 0 && q?.price != null) (q.price / selection - 1.0) * 100.0 else null
            Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                Text("入池价 ${selection?.let { String.format("%.2f", it) } ?: "—"}", fontSize = 10.sp, color = Muted)
                Text("至今 ${liveReturn?.let { String.format("%+.2f%%", it) } ?: "—"}", fontSize = 10.sp, color = liveReturn?.let(::pnl) ?: Muted)
            }
        }
    }
}

@Composable
fun HistoryStockRow(code: String, s: Snapshot, q: Quote?) {
    val meta = s.stocks[code]
    val perf = s.stockPerformance[code]
    Card(shape = RoundedCornerShape(15.dp)) {
        Column(Modifier.padding(12.dp)) {
            Row {
                Column(Modifier.weight(1f)) {
                    Text(meta?.name ?: q?.name ?: code, fontWeight = FontWeight.Bold)
                    Text(code, fontSize = 10.sp, color = Muted)
                }
                Text(s.pools.filterValues { code in it }.keys.sorted().joinToString(" "), fontSize = 10.sp, color = Blue)
            }
            Spacer(Modifier.height(6.dp))
            TrackingStrip(perf)
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
            Text(q?.quoteTime?.let { "行情 $it" } ?: "无时间戳", fontSize = 8.sp, color = Muted)
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
    Card(modifier, colors = CardDefaults.cardColors(containerColor = bg), shape = RoundedCornerShape(14.dp)) {
        Column(Modifier.padding(11.dp)) {
            Text(b.name, fontWeight = FontWeight.Bold, fontSize = 13.sp, maxLines = 1)
            Text(b.change?.let(::pct) ?: "—", color = b.change?.let(::pnl) ?: Muted, fontWeight = FontWeight.Bold)
            Text("广度 ${String.format("%.0f%%", breadth(b))}", fontSize = 9.sp, color = Muted)
            Text(b.flow?.let { "资金 ${signedMoney(it)}" } ?: "资金 —", fontSize = 9.sp, color = Muted, maxLines = 1)
        }
    }
}

@Composable
fun DateChip(s: Snapshot, selected: Boolean, modifier: Modifier, onClick: () -> Unit) {
    Card(
        modifier.clickable(onClick = onClick),
        colors = CardDefaults.cardColors(containerColor = if (selected) SoftBlue else if (s.status == "Official") SoftGreen else Color.White),
        shape = RoundedCornerShape(12.dp)
    ) {
        Column(Modifier.padding(8.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(s.date.substring(5), fontWeight = FontWeight.Bold, fontSize = 11.sp)
            Text(s.status.take(3), fontSize = 8.sp, color = if (s.status == "Official") Down else Amber)
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

@Composable
fun PerformanceCard(title: String, p: JSONObject?) {
    CardBlock {
        Text(title, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(6.dp))
        if (p == null || p.length() == 0) Text("尚未成熟 / 尚未同步", color = Muted, fontSize = 12.sp)
        else TrackingStrip(p)
    }
}

@Composable
fun TrackingStrip(p: JSONObject?) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(5.dp)) {
        listOf("1D", "5D", "10D", "20D", "60D").forEach { h ->
            Column(
                Modifier.weight(1f).background(Color(0xFFF3F5F9), RoundedCornerShape(8.dp)).padding(5.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(h, fontSize = 8.sp, color = Muted)
                Text(extractHorizon(p, h), fontSize = 9.sp, fontWeight = FontWeight.SemiBold)
            }
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
                label = { Text(item, fontSize = 10.sp) }
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

fun makePreview(boards: List<Board>): List<PreviewSector> {
    return boards.mapNotNull { b ->
        val change = b.change ?: return@mapNotNull null
        val br = breadth(b)
        val momentum = (50.0 + change * 8.0).coerceIn(0.0, 100.0)
        val flowScore = (50.0 + (b.flowPct ?: 0.0) * 4.0).coerceIn(0.0, 100.0)
        val score = 0.40 * momentum + 0.35 * br + 0.25 * flowScore
        val state = when {
            score >= 78.0 && change > 0 -> "Confirmed Candidate"
            score >= 65.0 -> "Candidate"
            else -> "Observe"
        }
        PreviewSector(b, score, state, momentum, br, flowScore)
    }.filter { it.score >= 60.0 }
        .sortedByDescending { it.score }
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
    if (quoteOkAt <= 0) return "行情 OFFLINE"
    val age = ((now - quoteOkAt).coerceAtLeast(0L) / 1000L)
    if (age > 15) return "行情 STALE ${age}s"
    val quoteTime = quotes.values.mapNotNull { it.quoteTime }.maxOrNull()
    return if (marketOpenNow()) "行情 LIVE ${age}s" else "行情 CLOSED ${quoteTime?.takeLast(6) ?: "已收盘"}"
}

fun freshnessLabel(now: Long, okAt: Long, staleMs: Long, live: String, stale: String): String {
    if (okAt <= 0) return "OFFLINE"
    val age = ((now - okAt).coerceAtLeast(0L) / 1000L)
    return if (now - okAt <= staleMs) "$live ${age}s" else "$stale ${age}s"
}

fun chinaClock(): String = LocalDateTime.now(CnZone).format(DateTimeFormatter.ofPattern("MM-dd HH:mm:ss"))

fun symbol(code: String): String = when {
    code.startsWith("6") || code.startsWith("68") -> "sh$code"
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

object DataApi {
    private const val SNAP = "https://raw.githubusercontent.com/cskjin940509-ops/cskjin/main/astock_snapshots/index.json"

    suspend fun fetchSnapshots(): List<Snapshot> = withContext(Dispatchers.IO) {
        val a = JSONArray(getText(SNAP))
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
                    quoteTime = f.getOrNull(30)
                )
            }
        }
        out
    }

    suspend fun fetchBoards(type: String): List<Board> = withContext(Dispatchers.IO) {
        val fs = if (type == "industry") "m:90+t:2+f:!50" else "m:90+t:3+f:!50"
        boardList(fs, type)
    }

    private fun boardList(fs0: String, type: String): List<Board> {
        val fs = URLEncoder.encode(fs0, "UTF-8")
        val url = "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=500&po=1&np=1&fltt=2&invt=2&fid=f3&fs=$fs&fields=f3,f6,f12,f14,f62,f184,f104,f105,f106"
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
        val pools = listOf("B0", "B1", "B2", "B3", "B4").associateWith { key -> arrStrings(poolsObj.optJSONArray(key)) }
        val stocks = linkedMapOf<String, StockMeta>()
        val stocksObj = o.optJSONObject("stocks")
        if (stocksObj != null) {
            val it = stocksObj.keys()
            while (it.hasNext()) {
                val code = it.next()
                val x = stocksObj.optJSONObject(code) ?: continue
                stocks[code] = StockMeta(
                    code,
                    x.optString("name").takeIf { it.isNotBlank() },
                    x.optString("sector").takeIf { it.isNotBlank() },
                    num(x, "RS") ?: num(x, "rs"),
                    x.optString("MTA").takeIf { it.isNotBlank() } ?: x.optString("mta").takeIf { it.isNotBlank() },
                    num(x, "score"),
                    x.optString("reason").takeIf { it.isNotBlank() },
                    num(x, "selectionPrice"),
                    x.optString("confidence").takeIf { it.isNotBlank() }
                )
            }
        }
        return Snapshot(
            date = date,
            status = o.optString("status", "Unknown"),
            regime = o.optString("regime", "Unknown"),
            strategyVersion = o.optString("strategyVersion").takeIf { it.isNotBlank() },
            mainlines = arrStrings(o.optJSONArray("mainlines")),
            pools = pools,
            stocks = stocks,
            poolPerformance = objMap(o.optJSONObject("poolPerformance") ?: o.optJSONObject("performance")),
            sectorPerformance = objMap(o.optJSONObject("sectorPerformance")),
            stockPerformance = objMap(o.optJSONObject("stockPerformance")),
            note = o.optString("note").takeIf { it.isNotBlank() }
        )
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
        c.setRequestProperty("User-Agent", "Mozilla/5.0 AStockStrategy/0.6")
        c.setRequestProperty("Cache-Control", "no-cache")
        c.connect()
        try {
            if (c.responseCode !in 200..299) error("HTTP ${c.responseCode}")
            return c.inputStream.use { it.readBytes() }
        } finally {
            c.disconnect()
        }
    }
}
