package com.rui.astockstrategy

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountTree
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Science
import androidx.compose.material.icons.filled.ShowChart
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
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.nio.charset.Charset
import java.text.DecimalFormat
import kotlin.math.abs

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

data class Sector(val name: String, val rs: Int, val breadth: Int, val status: String)

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
    val members: List<Member>
)

data class FundFlow(
    val time: String,
    val main: Double?,
    val large: Double?,
    val superLarge: Double?,
    val mid: Double?,
    val small: Double?
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

private val sectors = listOf(
    Sector("半导体设备", 94, 81, "Confirmed"),
    Sector("CPO/光通信", 92, 76, "Confirmed"),
    Sector("AI PCB", 87, 72, "Confirmed"),
    Sector("先进封装", 83, 68, "Candidate"),
    Sector("机器人", 74, 61, "Candidate"),
    Sector("创新药", 66, 55, "Rotation")
)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { StrategyApp() }
    }
}

enum class Tab(val label: String, val icon: ImageVector) {
    HOME("首页", Icons.Default.Home),
    MARKET("行情", Icons.Default.ShowChart),
    MAINLINE("主线", Icons.Default.AccountTree),
    POOLS("股票池", Icons.Default.ViewList),
    RESEARCH("研究", Icons.Default.Science)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StrategyApp() {
    var tab by remember { mutableStateOf(Tab.HOME) }
    var selectedStock by remember { mutableStateOf<Stock?>(null) }
    var selectedSector by remember { mutableStateOf<Sector?>(null) }
    var quotes by remember { mutableStateOf<Map<String, Quote>>(emptyMap()) }
    var dataStatus by remember { mutableStateOf("连接中") }

    val symbols = remember {
        listOf("sh000001", "sz399006", "sh000688", "sh000300", "sh000852") +
            stocks.map { marketSymbol(it.code) }
    }

    LaunchedEffect(Unit) {
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
                            Text("2026-08-18 · Preview（盘中预览）", fontSize = 11.sp, color = Amber)
                        }
                    },
                    actions = {
                        Text(
                            dataStatus,
                            fontSize = 11.sp,
                            color = if (dataStatus == "Live") Down else Amber,
                            modifier = Modifier.padding(end = 12.dp)
                        )
                    }
                )
            },
            bottomBar = {
                NavigationBar {
                    Tab.entries.forEach { item ->
                        NavigationBarItem(
                            selected = tab == item,
                            onClick = { tab = item },
                            icon = { Icon(item.icon, contentDescription = null) },
                            label = { Text(item.label) }
                        )
                    }
                }
            }
        ) { padding ->
            Box(Modifier.padding(padding).fillMaxSize()) {
                when (tab) {
                    Tab.HOME -> HomeScreen(quotes, { tab = it }, { selectedStock = it }, { selectedSector = it })
                    Tab.MARKET -> MarketScreen(quotes, { selectedStock = it }, { selectedSector = it })
                    Tab.MAINLINE -> MainlineScreen { selectedSector = it }
                    Tab.POOLS -> PoolsScreen(quotes) { selectedStock = it }
                    Tab.RESEARCH -> ResearchScreen()
                }
            }
        }

        selectedStock?.let { stock ->
            StockDetailDialog(stock, quotes[marketSymbol(stock.code)]) { selectedStock = null }
        }

        selectedSector?.let { sector ->
            SectorDetailDialog(
                sector = sector,
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
fun HomeScreen(
    quotes: Map<String, Quote>,
    go: (Tab) -> Unit,
    onStock: (Stock) -> Unit,
    onSector: (Sector) -> Unit
) {
    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                MetricCard("Regime", "震荡上行", "模型状态", Modifier.weight(1f))
                MetricCard("主线", "2 + 1", "确认 / 候选", Modifier.weight(1f))
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
                Text(
                    "进入行情看板",
                    color = Blue,
                    fontSize = 12.sp,
                    modifier = Modifier.padding(top = 10.dp).clickable { go(Tab.MARKET) }
                )
            }
        }
        item { SectionTitle("主线地图 · 点击查看板块详情") }
        items(sectors.take(3)) { SectorRow(it) { onSector(it) } }
        item { SectionTitle("B4 Combined · 点击查看个股详情") }
        items(stocks.filter { "B4" in it.pools }.take(6)) { stock ->
            StockRow(stock, quotes[marketSymbol(stock.code)]) { onStock(stock) }
        }
    }
}

@Composable
fun MarketScreen(quotes: Map<String, Quote>, onStock: (Stock) -> Unit, onSector: (Sector) -> Unit) {
    var mode by remember { mutableStateOf("指数") }
    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { ChoiceChips(listOf("指数", "板块", "个股"), mode) { mode = it } }
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
            "板块" -> items(sectors) { SectorRow(it) { onSector(it) } }
            else -> items(stocks) { stock ->
                StockRow(stock, quotes[marketSymbol(stock.code)]) { onStock(stock) }
            }
        }
    }
}

@Composable
fun MainlineScreen(onSector: (Sector) -> Unit) {
    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            SectionCard {
                Text("Mainline Engine（主线引擎）", fontWeight = FontWeight.Bold)
                Text("行业趋势 + 概念扩散 + RS + Breadth + 资金确认", color = Muted, fontSize = 12.sp)
            }
        }
        items(sectors) { SectorRow(it) { onSector(it) } }
    }
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
                Text("正式批次按收盘冻结；历史名单不事后改写", fontSize = 11.sp, color = Muted)
            }
        }
        items(list) { stock ->
            StockRow(stock, quotes[marketSymbol(stock.code)]) { onStock(stock) }
        }
    }
}

@Composable
fun ResearchScreen() {
    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            SectionCard {
                Text("Strategy Scorecard（策略成绩卡）", fontWeight = FontWeight.Bold)
                Text("1/5/10/20/60D Alpha、胜率、MFE/MAE、统计功效", color = Muted, fontSize = 12.sp)
            }
        }
        items(listOf("B0 Base", "B1 Margin", "B2 ETF", "B3 Main Flow", "B4 Combined")) { name ->
            SectionCard {
                Row {
                    Text(name, Modifier.weight(1f), fontWeight = FontWeight.SemiBold)
                    Text("Too Early", color = Amber)
                }
            }
        }
    }
}

@Composable
fun SectorDetailDialog(sector: Sector, onStock: (Member) -> Unit, onDismiss: () -> Unit) {
    var board by remember(sector.name) { mutableStateOf<Board?>(null) }
    var page by remember { mutableStateOf("概览") }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(sector.name) {
        runCatching { MarketData.fetchBoard(sector.name) }
            .onSuccess {
                board = it
                if (it == null) error = "公开行情源未精确匹配该板块，策略快照仍可查看"
            }
            .onFailure { error = "板块公开行情暂不可用" }
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = { TextButton(onClick = onDismiss) { Text("关闭") } },
        title = {
            Column {
                Text(sector.name)
                Text(
                    board?.change?.let(::formatPct) ?: "读取公开板块行情…",
                    color = board?.change?.let(::pnlColor) ?: Muted,
                    fontSize = 14.sp
                )
            }
        },
        text = {
            Column {
                ChoiceChips(listOf("概览", "成分", "资金", "策略"), page) { page = it }
                Spacer(Modifier.height(8.dp))
                LazyColumn(Modifier.heightIn(max = 500.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                    error?.let { item { Text(it, color = Amber, fontSize = 11.sp) } }
                    when (page) {
                        "概览" -> {
                            item { KeyValue("今日涨跌", board?.change?.let(::formatPct) ?: "—") }
                            item { KeyValue("成交额", board?.amount?.let(::formatMoney) ?: "—") }
                            item { KeyValue("上涨 / 下跌 / 平", board?.let { "${it.up} / ${it.down} / ${it.flat}" } ?: "—") }
                            item { KeyValue("模型 RS", sector.rs.toString()) }
                            item { KeyValue("模型 Breadth", "${sector.breadth}%") }
                        }
                        "成分" -> {
                            val members = board?.members.orEmpty()
                            if (members.isEmpty()) item { Text("加载中或暂无公开成分数据", color = Muted) }
                            items(members.take(40)) { member ->
                                Card(
                                    modifier = Modifier.fillMaxWidth().clickable { onStock(member) },
                                    colors = CardDefaults.cardColors(containerColor = Color(0xFFF8F9FC))
                                ) {
                                    Row(Modifier.padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
                                        Column(Modifier.weight(1f)) {
                                            Text(member.name, fontWeight = FontWeight.SemiBold)
                                            Text(member.code, fontSize = 10.sp, color = Muted)
                                        }
                                        Column(horizontalAlignment = Alignment.End) {
                                            Text(member.price?.let { DecimalFormat("0.00").format(it) } ?: "—")
                                            Text(member.change?.let(::formatPct) ?: "—", color = member.change?.let(::pnlColor) ?: Muted)
                                        }
                                    }
                                }
                            }
                        }
                        "资金" -> {
                            item { KeyValue("主力净流", board?.flow?.let(::formatSignedMoney) ?: "—") }
                            item { KeyValue("主力净流占比", board?.flowPct?.let(::formatPct) ?: "—") }
                            item { Text("主力/大单来自公开成交单分类算法，属于实验性数据，不等于机构账户真实买卖。", fontSize = 10.sp, color = Muted) }
                        }
                        else -> {
                            item { KeyValue("主线状态", sector.status) }
                            item { KeyValue("RS", sector.rs.toString()) }
                            item { KeyValue("Breadth", "${sector.breadth}%") }
                            item { Text("实时行情事实与策略冻结判断分栏展示，盘中涨跌不会改写历史策略快照。", fontSize = 10.sp, color = Muted) }
                        }
                    }
                }
            }
        }
    )
}

@Composable
fun StockDetailDialog(stock: Stock, initialQuote: Quote?, onDismiss: () -> Unit) {
    var quote by remember(stock.code) { mutableStateOf(initialQuote) }
    var flow by remember(stock.code) { mutableStateOf<FundFlow?>(null) }
    var page by remember { mutableStateOf("概览") }

    LaunchedEffect(stock.code) {
        if (quote == null) {
            runCatching { MarketData.fetchQuotes(listOf(marketSymbol(stock.code))) }
                .onSuccess { quote = it[marketSymbol(stock.code)] }
        }
        runCatching { MarketData.fetchFundFlow(stock.code) }.onSuccess { flow = it }
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = { TextButton(onClick = onDismiss) { Text("关闭") } },
        title = {
            Column {
                Text("${stock.name}  ${stock.code}")
                Row(verticalAlignment = Alignment.Bottom) {
                    Text(quote?.price?.let { DecimalFormat("0.00").format(it) } ?: "—", fontWeight = FontWeight.Bold, fontSize = 20.sp)
                    Text("  ${quote?.change?.let(::formatPct) ?: ""}", color = quote?.change?.let(::pnlColor) ?: Muted)
                }
            }
        },
        text = {
            Column {
                ChoiceChips(listOf("概览", "趋势", "资金", "策略"), page) { page = it }
                Spacer(Modifier.height(8.dp))
                LazyColumn(Modifier.heightIn(max = 480.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
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
                            item { Text("下一版补交互K线、MA20D / MA20W / MA10M 与历史 Alpha 曲线。", fontSize = 10.sp, color = Muted) }
                        }
                        "资金" -> {
                            if (flow == null) {
                                item { Text("资金数据加载中或公开接口暂不可用", color = Muted) }
                            } else {
                                item { KeyValue("时间", flow!!.time) }
                                item { KeyValue("主力净流", flow!!.main?.let(::formatSignedMoney) ?: "—") }
                                item { KeyValue("超大单", flow!!.superLarge?.let(::formatSignedMoney) ?: "—") }
                                item { KeyValue("大单", flow!!.large?.let(::formatSignedMoney) ?: "—") }
                                item { KeyValue("中单", flow!!.mid?.let(::formatSignedMoney) ?: "—") }
                                item { KeyValue("小单", flow!!.small?.let(::formatSignedMoney) ?: "—") }
                            }
                            item { Text("主力/大单为 C 级算法分类数据；两融正式策略信号按披露时点使用。", fontSize = 10.sp, color = Muted) }
                        }
                        else -> {
                            item { KeyValue("出现池", if (stock.pools.isEmpty()) "未入策略池" else stock.pools.sorted().joinToString(" / ")) }
                            item { KeyValue("状态", if (stock.pools.isEmpty()) "Market" else "Active") }
                            item { Text("入池逻辑", fontWeight = FontWeight.Bold) }
                            item { Text(stock.reason, fontSize = 12.sp, color = Muted) }
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
        Column(Modifier.padding(14.dp)) {
            Text(title, fontSize = 11.sp, color = Muted)
            Text(value, fontWeight = FontWeight.Bold, fontSize = 19.sp)
            Text(subtitle, fontSize = 10.sp, color = Muted)
        }
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
    Column {
        Text(name, fontSize = 11.sp, color = Muted)
        Text(quote?.price?.let { DecimalFormat("0.00").format(it) } ?: "—", fontWeight = FontWeight.Bold)
        Text(quote?.change?.let(::formatPct) ?: "—", color = quote?.change?.let(::pnlColor) ?: Muted, fontSize = 11.sp)
    }
}

@Composable
fun QuoteLine(name: String, quote: Quote?) {
    Row(Modifier.fillMaxWidth().padding(vertical = 7.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(name, Modifier.weight(1f))
        Text(quote?.price?.let { DecimalFormat("0.00").format(it) } ?: "—", fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.width(12.dp))
        Text(quote?.change?.let(::formatPct) ?: "—", color = quote?.change?.let(::pnlColor) ?: Muted)
    }
}

@Composable
fun SectorRow(sector: Sector, onClick: () -> Unit) {
    Card(Modifier.fillMaxWidth().clickable(onClick = onClick), shape = RoundedCornerShape(16.dp)) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(sector.name, fontWeight = FontWeight.Bold)
                Text("${sector.status} · Breadth ${sector.breadth}%", fontSize = 11.sp, color = Muted)
            }
            Text("RS ${sector.rs}", color = Blue, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
fun StockRow(stock: Stock, quote: Quote?, onClick: () -> Unit) {
    Card(Modifier.fillMaxWidth().clickable(onClick = onClick), shape = RoundedCornerShape(16.dp)) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(stock.name, fontWeight = FontWeight.Bold)
                Text("${stock.code} · ${stock.line}", fontSize = 11.sp, color = Muted)
                Text(stock.pools.sorted().joinToString(" "), fontSize = 10.sp, color = Blue)
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(quote?.price?.let { DecimalFormat("0.00").format(it) } ?: "—", fontWeight = FontWeight.Bold)
                Text(quote?.change?.let(::formatPct) ?: "—", color = quote?.change?.let(::pnlColor) ?: Muted, fontSize = 11.sp)
                if (stock.rs > 0) Text("RS ${stock.rs}", fontSize = 10.sp, color = Blue)
            }
        }
    }
}

@Composable
fun ChoiceChips(values: List<String>, selected: String, onSelect: (String) -> Unit) {
    LazyRow(horizontalArrangement = Arrangement.spacedBy(7.dp)) {
        items(values) { value ->
            FilterChip(selected = value == selected, onClick = { onSelect(value) }, label = { Text(value) })
        }
    }
}

@Composable
fun KeyValue(key: String, value: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(key, fontSize = 12.sp, color = Muted)
        Spacer(Modifier.width(12.dp))
        Text(value, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
    }
}

object MarketData {
    suspend fun fetchQuotes(symbols: List<String>): Map<String, Quote> = withContext(Dispatchers.IO) {
        val connection = (URL("https://qt.gtimg.cn/q=${symbols.distinct().joinToString(",")}").openConnection() as HttpURLConnection).apply {
            connectTimeout = 7000
            readTimeout = 7000
            setRequestProperty("User-Agent", "Mozilla/5.0 Android AStockStrategy")
        }
        try {
            val text = connection.inputStream.use { it.readBytes() }.toString(Charset.forName("GBK"))
            val output = linkedMapOf<String, Quote>()
            val regex = Regex("v_([a-zA-Z0-9]+)=\\\"([^\\\"]*)\\\"")
            regex.findAll(text).forEach { match ->
                val fields = match.groupValues[2].split("~")
                if (fields.size > 37) {
                    val symbol = match.groupValues[1]
                    output[symbol] = Quote(
                        symbol = symbol,
                        name = fields.getOrNull(1).orEmpty(),
                        code = fields.getOrNull(2).orEmpty(),
                        price = fields.getOrNull(3)?.toDoubleOrNull(),
                        prev = fields.getOrNull(4)?.toDoubleOrNull(),
                        change = fields.getOrNull(32)?.toDoubleOrNull(),
                        high = fields.getOrNull(33)?.toDoubleOrNull(),
                        low = fields.getOrNull(34)?.toDoubleOrNull(),
                        amount = fields.getOrNull(37)?.toDoubleOrNull()?.times(10_000),
                        time = fields.getOrNull(30)
                    )
                }
            }
            output
        } finally {
            connection.disconnect()
        }
    }

    suspend fun fetchBoard(name: String): Board? = withContext(Dispatchers.IO) {
        val candidates = boardList("m:90+t:2+f:!50") + boardList("m:90+t:3+f:!50")
        val found = candidates.firstOrNull { it.name == name }
            ?: candidates.firstOrNull { it.name.contains(name) || name.contains(it.name) }
            ?: return@withContext null
        found.copy(members = members(found.code))
    }

    suspend fun fetchFundFlow(code: String): FundFlow? = withContext(Dispatchers.IO) {
        val market = if (code.startsWith("6") || code.startsWith("5") || code.startsWith("9")) "1" else "0"
        val url = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get?secid=$market.$code&klt=1&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57"
        val klines = getJson(url).optJSONObject("data")?.optJSONArray("klines") ?: return@withContext null
        if (klines.length() == 0) return@withContext null
        val parts = klines.optString(klines.length() - 1).split(",")
        FundFlow(
            time = parts.getOrNull(0).orEmpty(),
            main = parts.getOrNull(1)?.toDoubleOrNull(),
            small = parts.getOrNull(2)?.toDoubleOrNull(),
            mid = parts.getOrNull(3)?.toDoubleOrNull(),
            large = parts.getOrNull(4)?.toDoubleOrNull(),
            superLarge = parts.getOrNull(5)?.toDoubleOrNull()
        )
    }

    private fun boardList(fs: String): List<Board> {
        val url = "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=500&po=1&np=1&fltt=2&invt=2&fid=f3&fs=${URLEncoder.encode(fs, "UTF-8")}&fields=f3,f6,f12,f14,f62,f184,f104,f105,f106"
        val array = getJson(url).optJSONObject("data")?.optJSONArray("diff") ?: return emptyList()
        val result = mutableListOf<Board>()
        for (i in 0 until array.length()) {
            val item = array.optJSONObject(i) ?: continue
            result += Board(
                code = item.optString("f12"),
                name = item.optString("f14"),
                change = number(item, "f3"),
                amount = number(item, "f6"),
                flow = number(item, "f62"),
                flowPct = number(item, "f184"),
                up = item.optInt("f104"),
                down = item.optInt("f105"),
                flat = item.optInt("f106"),
                members = emptyList()
            )
        }
        return result
    }

    private fun members(boardCode: String): List<Member> {
        val fs = URLEncoder.encode("b:$boardCode", "UTF-8")
        val url = "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=100&po=1&np=1&fltt=2&invt=2&fid=f3&fs=$fs&fields=f2,f3,f6,f12,f14,f62"
        val array = getJson(url).optJSONObject("data")?.optJSONArray("diff") ?: return emptyList()
        val result = mutableListOf<Member>()
        for (i in 0 until array.length()) {
            val item = array.optJSONObject(i) ?: continue
            result += Member(
                code = item.optString("f12"),
                name = item.optString("f14"),
                price = number(item, "f2"),
                change = number(item, "f3"),
                amount = number(item, "f6"),
                flow = number(item, "f62")
            )
        }
        return result
    }

    private fun getJson(url: String): JSONObject {
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 8000
            readTimeout = 10000
            setRequestProperty("User-Agent", "Mozilla/5.0 Android AStockStrategy")
            setRequestProperty("Referer", "https://quote.eastmoney.com/")
        }
        return try {
            JSONObject(connection.inputStream.bufferedReader().use { it.readText() })
        } finally {
            connection.disconnect()
        }
    }

    private fun number(json: JSONObject, key: String): Double? {
        if (!json.has(key) || json.isNull(key)) return null
        val value = json.optDouble(key, Double.NaN)
        return if (value.isNaN()) null else value
    }
}

private fun marketSymbol(code: String): String =
    if (code.startsWith("6") || code.startsWith("5") || code.startsWith("9")) "sh$code" else "sz$code"

private fun formatPct(value: Double): String = (if (value >= 0) "+" else "") + String.format("%.2f%%", value)
private fun pnlColor(value: Double): Color = if (value >= 0) Up else Down

private fun formatMoney(value: Double): String = when {
    abs(value) >= 1e12 -> String.format("%.2f万亿", value / 1e12)
    abs(value) >= 1e8 -> String.format("%.2f亿", value / 1e8)
    abs(value) >= 1e4 -> String.format("%.1f万", value / 1e4)
    else -> DecimalFormat("#,##0").format(value)
}

private fun formatSignedMoney(value: Double): String {
    val body = formatMoney(abs(value))
    return if (value < 0) "-$body" else "+$body"
}

private fun poolName(pool: String): String = when (pool) {
    "B0" -> "B0 Base（基础池）"
    "B1" -> "B1 Margin（两融增强）"
    "B2" -> "B2 ETF（ETF增强）"
    "B3" -> "B3 Main Flow（主力增强）"
    else -> "B4 Combined（联合池）"
}
