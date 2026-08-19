from pathlib import Path
import re

# This patch runs LAST, after v1.9/audit/tail patches. It repairs any earlier
# patch-order regressions and makes the data contract explicit in the UI.

p = Path('app/src/main/java/com/rui/astockstrategy/v6/V6Activity.kt')
s = p.read_text(encoding='utf-8')

# Board may carry a known breadth percentage even when raw up/down counts are
# unavailable (e.g. a Tail snapshot). Existing constructors remain compatible.
s = s.replace(
'''data class Board(
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
)''',
'''data class Board(
    val code: String,
    val name: String,
    val change: Double?,
    val amount: Double?,
    val flow: Double?,
    val flowPct: Double?,
    val up: Int,
    val down: Int,
    val flat: Int,
    val type: String,
    val breadthOverride: Double? = null
)'''
)

# Rich frozen sector metadata instead of name-only selectedSectors.
if 'data class SelectedSectorMeta(' not in s:
    marker = 'data class Snapshot('
    block = '''data class SelectedSectorMeta(
    val code: String,
    val name: String,
    val type: String?,
    val score: Double?,
    val status: String?,
    val changePct: Double?,
    val amount: Double?,
    val mainNetFlow: Double?,
    val mainFlowPct: Double?,
    val breadthPct: Double?,
    val rs20: Double?,
    val rs60: Double?,
    val mta: String?,
    val confidence: String?,
    val reason: String?
)

'''
    if marker not in s:
        raise SystemExit('Snapshot model marker missing')
    s = s.replace(marker, block + marker, 1)

# Extend StockMeta with frozen facts and price-validation provenance.
s = s.replace(
'''    val selectionPrice: Double?,
    val dayChangePct: Double?,
    val confidence: String?
)''',
'''    val selectionPrice: Double?,
    val dayChangePct: Double?,
    val rs60: Double?,
    val amount: Double?,
    val turnover: Double?,
    val mainNetFlow: Double?,
    val mainFlowPct: Double?,
    val priceProviders: List<String>,
    val priceMaxRelDiff: Double?,
    val confidence: String?
)''',
1,
)

# Extend Snapshot with formal-sector details, factor availability and tracking/data validation status.
s = s.replace(
'''    val selectedSectors: List<String>,
    val pools: Map<String, List<String>>,''',
'''    val selectedSectors: List<String>,
    val selectedSectorDetails: List<SelectedSectorMeta>,
    val factorAvailability: Map<String, String>,
    val trackingDisplayStatus: String?,
    val trackingDisplayNote: String?,
    val trackingUpdatedAt: String?,
    val validationStatus: String?,
    val validationProviders: List<String>,
    val pools: Map<String, List<String>>,''',
1,
)

# Parse all frozen stock fields that already exist in the production JSON.
s = s.replace(
'''                    num(x, "selectionPrice"),
                    num(x, "changePct"),
                    x.optString("confidence").takeIf { it.isNotBlank() }''',
'''                    num(x, "selectionPrice"),
                    num(x, "changePct"),
                    num(x, "RS60") ?: num(x, "rs60"),
                    num(x, "amount"),
                    num(x, "turnover"),
                    num(x, "mainNetFlow"),
                    num(x, "mainFlowPct"),
                    arrStrings(x.optJSONObject("priceValidation")?.optJSONArray("providers")),
                    x.optJSONObject("priceValidation")?.let { num(it, "maxRelDiff") },
                    x.optString("confidence").takeIf { it.isNotBlank() }''',
1,
)

# Snapshot parser additions.
s = s.replace(
'''            selectedSectors = arrObjectNames(o.optJSONArray("selectedSectors")),
            pools = pools,''',
'''            selectedSectors = arrObjectNames(o.optJSONArray("selectedSectors")),
            selectedSectorDetails = parseSelectedSectorDetails(o.optJSONArray("selectedSectors")),
            factorAvailability = stringMap(o.optJSONObject("factorAvailability")),
            trackingDisplayStatus = o.optString("trackingDisplayStatus").takeIf { it.isNotBlank() },
            trackingDisplayNote = o.optString("trackingDisplayNote").takeIf { it.isNotBlank() },
            trackingUpdatedAt = o.optString("trackingUpdatedAt").takeIf { it.isNotBlank() },
            validationStatus = o.optJSONObject("dataValidation")?.optString("status")?.takeIf { it.isNotBlank() },
            validationProviders = arrStrings(o.optJSONObject("dataValidation")?.optJSONArray("priceProviders")),
            pools = pools,''',
1,
)

# Rich parser helpers.
marker = '    private fun arrObjectNames(a: JSONArray?): List<String> {'
helpers = '''    private fun parseSelectedSectorDetails(a: JSONArray?): List<SelectedSectorMeta> {
        if (a == null) return emptyList()
        return (0 until a.length()).mapNotNull { i ->
            val x = a.optJSONObject(i) ?: return@mapNotNull null
            val name = x.optString("name")
            if (name.isBlank()) return@mapNotNull null
            SelectedSectorMeta(
                code = x.optString("boardCode"),
                name = name,
                type = x.optString("type").takeIf { it.isNotBlank() },
                score = num(x, "score"),
                status = x.optString("status").takeIf { it.isNotBlank() },
                changePct = num(x, "changePct"),
                amount = num(x, "amount"),
                mainNetFlow = num(x, "mainNetFlow"),
                mainFlowPct = num(x, "mainFlowPct"),
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
            val v = o.optString(k)
            if (v.isNotBlank()) out[k] = v
        }
        return out
    }

'''
if 'private fun parseSelectedSectorDetails' not in s:
    if marker not in s:
        raise SystemExit('arrObjectNames marker missing')
    s = s.replace(marker, helpers + marker, 1)

# Breadth should respect a source-provided percentage when counts are unavailable.
s = s.replace(
'''fun breadth(b: Board): Double {
    val total = b.up + b.down + b.flat
    return if (total <= 0) 50.0 else b.up.toDouble() / total.toDouble() * 100.0
}''',
'''fun breadth(b: Board): Double {
    b.breadthOverride?.let { return it.coerceIn(0.0, 100.0) }
    val total = b.up + b.down + b.flat
    return if (total <= 0) 50.0 else b.up.toDouble() / total.toDouble() * 100.0
}'''
)

# Replace Official/Preview mainline screen. This intentionally uses
# selectedSectors even if the stricter confirmed mainline list is empty.
pattern = re.compile(r'@Composable\nfun MainlineScreen\(s: Snapshot\?, preview: List<PreviewSector>, now: Long, boardOkAt: Long\) \{.*?\n\}\n\n@Composable\nfun PoolsScreen', re.S)
mainline = '''@Composable
fun MainlineScreen(s: Snapshot?, preview: List<PreviewSector>, now: Long, boardOkAt: Long) {
    var mode by remember { mutableStateOf("盘中Preview") }
    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { Choice(listOf("盘中Preview", "Official"), mode) { mode = it } }
        if (mode == "盘中Preview") {
            item { Notice("实时主线候选随公开板块行情重新计算；这是 Preview，不写入历史。点任意板块可查看趋势、资金、广度和成分股。") }
            item { LiveBadge("Mainline Preview", freshnessLabel(now, boardOkAt, 70000, "实时", "已过期"), now - boardOkAt <= 70000, Modifier.fillMaxWidth()) }
            if (preview.isEmpty()) item { EmptyCard("等待实时板块数据") }
            else items(preview.take(12)) { PreviewRadar(it) }
        } else {
            if (s == null) {
                item { EmptyCard("暂无 Official Snapshot") }
            } else {
                item { Notice("${s.date} ${snapshotAuditLabel(s)}：收盘筛选结果已冻结。确认主线和正式候选板块分开显示，不会把“观察”冒充确认主线。") }
                if (!s.performanceEligible) item { AuditWarning(s) }
                if (s.mainlines.isNotEmpty()) {
                    item { Title("确认主线") }
                    val confirmedDetails = s.selectedSectorDetails.filter { it.name in s.mainlines }
                    if (confirmedDetails.isNotEmpty()) items(confirmedDetails) { OfficialSectorRow(it, s.date, true) }
                    else items(s.mainlines) { name -> OfficialSectorNameRow(name, s.date, true) }
                } else {
                    item { Notice("当日没有板块达到更严格的“确认主线”阈值，但正式收盘筛选仍产生了候选板块和股票池。") }
                }
                item { Title("正式收盘筛选板块") }
                val rest = s.selectedSectorDetails.filter { it.name !in s.mainlines }
                when {
                    rest.isNotEmpty() -> items(rest) { OfficialSectorRow(it, s.date, false) }
                    s.selectedSectors.isNotEmpty() -> items(s.selectedSectors.filter { it !in s.mainlines }) { name -> OfficialSectorNameRow(name, s.date, false) }
                    else -> item { EmptyCard("该日没有达到正式筛选阈值的板块") }
                }
            }
        }
    }
}

@Composable
fun OfficialSectorRow(x: SelectedSectorMeta, date: String, confirmed: Boolean) {
    Card(Modifier.fillMaxWidth().clickable { DetailNav.openSectorName(x.name, date) }, shape = RoundedCornerShape(16.dp)) {
        Column(Modifier.fillMaxWidth().padding(13.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Row(verticalAlignment = Alignment.Top) {
                Column(Modifier.weight(1f)) {
                    Text(x.name, fontWeight = FontWeight.Bold)
                    Text("${x.type ?: "板块"} · ${x.status ?: if (confirmed) "确认主线" else "正式筛选"} · 点开详情", fontSize = 10.sp, color = Muted)
                }
                Text(x.score?.let { String.format("%.1f", it) } ?: "—", fontWeight = FontWeight.Bold, color = if (confirmed) Up else Blue)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("涨跌 ${x.changePct?.let(::pct) ?: "—"}", fontSize = 9.sp, color = x.changePct?.let(::pnl) ?: Muted)
                Text("资金占比 ${x.mainFlowPct?.let(::pct) ?: "—"}", fontSize = 9.sp, color = Muted)
                Text("广度 ${x.breadthPct?.let { String.format("%.0f%%", it) } ?: "—"}", fontSize = 9.sp, color = Muted)
            }
            Text("${x.mta ?: "趋势待同步"} · 置信度 ${x.confidence ?: "—"}", fontSize = 9.sp, color = Muted)
        }
    }
}

@Composable
fun OfficialSectorNameRow(name: String, date: String, confirmed: Boolean) {
    Card(Modifier.fillMaxWidth().clickable { DetailNav.openSectorName(name, date) }, shape = RoundedCornerShape(16.dp)) {
        Column(Modifier.fillMaxWidth().padding(13.dp)) {
            Text(name, fontWeight = FontWeight.Bold)
            Text("${if (confirmed) "确认主线" else "正式筛选板块"} · $date · 点开详情", fontSize = 10.sp, color = Muted)
        }
    }
}

@Composable
fun PoolsScreen'''
s, n = pattern.subn(mainline, s, count=1)
if n != 1:
    raise SystemExit('MainlineScreen replacement failed')

# Replace pool screen so frozen facts, signal-day move and real forward tracking
# are all visible at the same time.
pattern = re.compile(r'@Composable\nfun PoolsScreen\(s: Snapshot\?, quotes: Map<String, Quote>, now: Long, quoteOkAt: Long\) \{.*?\n\}\n\n@Composable\nfun HistoryScreen', re.S)
pools_screen = '''@Composable
fun PoolsScreen(s: Snapshot?, quotes: Map<String, Quote>, now: Long, quoteOkAt: Long) {
    if (s == null) { Empty("暂无正式股票池快照"); return }
    var pool by remember(s.date) { mutableStateOf("B4") }
    val codes = s.pools[pool].orEmpty()
    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
        item { PoolSelector(pool) { pool = it } }
        item { Notice("${poolTitle(pool)} 来自 ${s.date} 的 ${snapshotAuditLabel(s)}。名单冻结；收盘当天涨跌、实时/最近价和次日开盘后的策略 Tracking 分开显示。") }
        s.factorAvailability[pool]?.let { item { Notice("因子状态：$it") } }
        item { LiveBadge("Pool Quotes", freshnessLabel(now, quoteOkAt, 15000, "实时", "已过期"), marketStateOk(now, quoteOkAt), Modifier.fillMaxWidth()) }
        item { PoolReturnSummary(s, pool) }
        if (codes.isEmpty()) item { EmptyCard("${poolTitle(pool)} 当前为空；必要因子缺失时不会用替代口径伪造名单。") }
        else items(codes) { code -> StockLiveRow(code, s, quotes[symbol(code)]) }
        item { PerformanceCard("${poolTitle(pool)} Forward Tracking（次日开盘起算）", s.poolPerformance[pool]) }
        if (!s.performanceEligible && (s.poolPerformance[pool]?.length() ?: 0) > 0) item { Notice("当前批次的 Tracking 仅作为价格路径参考，不进入胜率、Alpha或因子有效性统计。") }
    }
}

@Composable
fun HistoryScreen'''
s, n = pattern.subn(pools_screen, s, count=1)
if n != 1:
    raise SystemExit('PoolsScreen replacement failed')

# Restore clickability that an earlier returns patch could overwrite, and expose
# the frozen stock facts even when direct live quotes are unavailable.
pattern = re.compile(r'@Composable\nfun StockLiveRow\(code: String, s: Snapshot, q: Quote\?\) \{.*?\n\}\n\n@Composable\nfun HistoryStockRow', re.S)
stock_row = '''@Composable
fun StockLiveRow(code: String, s: Snapshot, q: Quote?) {
    val meta = s.stocks[code]
    val perf = s.stockPerformance[code]
    val tracking = jsonReturn(perf?.optJSONObject("current"))
    val shownPrice = q?.price ?: meta?.selectionPrice
    val shownMove = q?.change ?: meta?.dayChangePct
    Card(Modifier.fillMaxWidth().clickable { DetailNav.openStock(code, s.date) }, shape = RoundedCornerShape(15.dp)) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row {
                Column(Modifier.weight(1f)) {
                    Text(meta?.name ?: q?.name ?: code, fontWeight = FontWeight.Bold)
                    Text("$code · ${meta?.sector ?: "—"} · 点开详情", fontSize = 10.sp, color = Muted)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(shownPrice?.let { String.format("%.2f", it) } ?: "—", fontWeight = FontWeight.Bold)
                    Text(shownMove?.let(::pct) ?: "—", color = shownMove?.let(::pnl) ?: Muted, fontSize = 11.sp)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("信号日 ${meta?.dayChangePct?.let(::pct) ?: "—"}", fontSize = 9.sp, color = meta?.dayChangePct?.let(::pnl) ?: Muted)
                Text("入池价 ${meta?.selectionPrice?.let { String.format("%.2f", it) } ?: "—"}", fontSize = 9.sp, color = Muted)
                Text("评分 ${meta?.score?.let { String.format("%.1f", it) } ?: "—"}", fontSize = 9.sp, color = Muted)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("主力 ${meta?.mainFlowPct?.let(::pct) ?: "—"}", fontSize = 9.sp, color = Muted)
                Text("换手 ${meta?.turnover?.let { String.format("%.1f%%", it) } ?: "—"}", fontSize = 9.sp, color = Muted)
                Text("Tracking ${tracking?.let { pct(it * 100.0) } ?: "待次日开盘"}", fontSize = 9.sp, color = tracking?.let { pnl(it) } ?: Muted)
            }
            if (meta?.priceProviders?.isNotEmpty() == true) {
                Text("收盘价核对 ${meta.priceProviders.joinToString("+")} · 最大差 ${meta.priceMaxRelDiff?.let { String.format("%.3f%%", it * 100.0) } ?: "—"}", fontSize = 8.sp, color = Muted)
            }
        }
    }
}

@Composable
fun HistoryStockRow'''
s, n = pattern.subn(stock_row, s, count=1)
if n != 1:
    raise SystemExit('StockLiveRow replacement failed')

pattern = re.compile(r'@Composable\nfun HistoryStockRow\(code: String, s: Snapshot, q: Quote\?\) \{.*?\n\}\n\n@Composable\nfun IndexCard', re.S)
history_row = '''@Composable
fun HistoryStockRow(code: String, s: Snapshot, q: Quote?) {
    val meta = s.stocks[code]
    val perf = s.stockPerformance[code]
    val current = jsonReturn(perf?.optJSONObject("current"))
    val entryDate = perf?.optString("entryDate")?.takeIf { it.isNotBlank() }
    val entryPrice = jsonNumber(perf, "entryPrice")
    Card(Modifier.fillMaxWidth().clickable { DetailNav.openStock(code, s.date) }, shape = RoundedCornerShape(15.dp)) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row {
                Column(Modifier.weight(1f)) {
                    Text(meta?.name ?: q?.name ?: code, fontWeight = FontWeight.Bold)
                    Text("$code · ${meta?.sector ?: "—"} · 点开详情", fontSize = 10.sp, color = Muted)
                }
                Text(s.pools.filterValues { code in it }.keys.sorted().joinToString(" "), fontSize = 10.sp, color = Blue)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("信号日 ${meta?.dayChangePct?.let(::pct) ?: "—"}", fontSize = 9.sp, color = meta?.dayChangePct?.let(::pnl) ?: Muted)
                Text("次日入场 ${entryDate ?: "待成熟"}", fontSize = 9.sp, color = Muted)
                Text("入场价 ${entryPrice?.let { String.format("%.2f", it) } ?: "—"}", fontSize = 9.sp, color = Muted)
            }
            Text("策略跟踪 ${current?.let { pct(it * 100.0) } ?: "—"}", fontSize = 10.sp, fontWeight = FontWeight.SemiBold, color = current?.let { pnl(it) } ?: Muted)
            if (perf != null && perf.length() > 0) {
                TrackingStrip(perf)
                if (!s.performanceEligible) Text("参考 Tracking · 不进入模型成绩统计", fontSize = 9.sp, color = Amber)
            } else Text("从信号后下一交易日可成交开盘起算，尚未成熟时保持空值。", fontSize = 9.sp, color = Muted)
        }
    }
}

@Composable
fun IndexCard'''
s, n = pattern.subn(history_row, s, count=1)
if n != 1:
    raise SystemExit('HistoryStockRow replacement failed')

# Replace pool summary with a transparent separation of signal-day movement vs strategy return.
pattern = re.compile(r'@Composable\nfun PoolReturnSummary\(s: Snapshot, pool: String\) \{.*?\n\}\n\n', re.S)
pool_summary = '''@Composable
fun PoolReturnSummary(s: Snapshot, pool: String) {
    val codes = s.pools[pool].orEmpty()
    val moves = codes.mapNotNull { s.stocks[it]?.dayChangePct }
    val signalDayAvg = moves.takeIf { it.isNotEmpty() }?.average()
    val current = jsonReturn(s.poolPerformance[pool]?.optJSONObject("current"))
    val oneDay = jsonReturn(s.poolPerformance[pool]?.optJSONObject("1D"))
    CardBlock {
        Text("收益与数据状态", fontWeight = FontWeight.Bold)
        Key("信号日等权涨跌", signalDayAvg?.let(::pct) ?: "—")
        Key("策略当前 Tracking", current?.let { pct(it * 100.0) } ?: "等待下一交易日可成交开盘")
        Key("成熟 1D", oneDay?.let { pct(it * 100.0) } ?: "—")
        Key("价格验证", listOfNotNull(s.validationStatus, s.validationProviders.takeIf { it.isNotEmpty() }?.joinToString("+")).joinToString(" · ").ifBlank { "—" })
        s.factorAvailability[pool]?.let { Key("因子可用性", it) }
        Text("信号日涨跌是筛选前当天已发生的行情；策略收益严格从下一交易日可成交开盘开始。", fontSize = 9.sp, color = Muted)
    }
}

'''
s, n = pattern.subn(pool_summary, s, count=1)
if n != 1:
    raise SystemExit('PoolReturnSummary replacement failed')

# Add generic numeric helper next to jsonReturn.
if 'fun jsonNumber(o: JSONObject?' not in s:
    marker = 'fun jsonReturn(o: JSONObject?): Double? {'
    helper = '''fun jsonNumber(o: JSONObject?, key: String): Double? {
    if (o == null) return null
    val v = o.opt(key)
    return when (v) {
        null, JSONObject.NULL -> null
        is Number -> v.toDouble()
        else -> v.toString().toDoubleOrNull()
    }
}

'''
    s = s.replace(marker, helper + marker, 1)

p.write_text(s, encoding='utf-8')

# ---- Detail screens -------------------------------------------------------
d = Path('app/src/main/java/com/rui/astockstrategy/v6/DetailScreens.kt')
ds = d.read_text(encoding='utf-8')

# Preserve Tail context when drilling into a TailLive/TailFinal stock.
ds = ds.replace(
'''    var stockCode by mutableStateOf<String?>(null)
    var stockDate by mutableStateOf<String?>(null)''',
'''    var stockCode by mutableStateOf<String?>(null)
    var stockDate by mutableStateOf<String?>(null)
    var tailStock by mutableStateOf<TailStock?>(null)''',
1,
)
ds = ds.replace(
'''    fun openStock(code: String, date: String?) {
        stockCode = code
        stockDate = date
    }''',
'''    fun openStock(code: String, date: String?) {
        stockCode = code
        stockDate = date
        tailStock = null
    }

    fun openTailStock(stock: TailStock, date: String?) {
        stockCode = stock.code
        stockDate = date
        tailStock = stock
    }''',
1,
)
ds = ds.replace('''            stockCode = null
            stockDate = null''', '''            stockCode = null
            stockDate = null
            tailStock = null''', 1)
ds = ds.replace('''        stockCode = null
        stockDate = null
    }''', '''        stockCode = null
        stockDate = null
        tailStock = null
    }''', 1)

# Price validation fields on frozen stock facts.
ds = ds.replace(
'''    val mainFlowPct: Double?,
    val pools: List<String>
)''',
'''    val mainFlowPct: Double?,
    val pools: List<String>,
    val priceProviders: List<String>,
    val priceMaxRelDiff: Double?
)''',
1,
)
ds = ds.replace(
'''            mainFlowPct = jsonNum(x, "mainFlowPct"),
            pools = ps.distinct().sorted()
        )''',
'''            mainFlowPct = jsonNum(x, "mainFlowPct"),
            pools = ps.distinct().sorted(),
            priceProviders = run {
                val a = x.optJSONObject("priceValidation")?.optJSONArray("providers")
                if (a == null) emptyList() else (0 until a.length()).mapNotNull { i -> a.optString(i).takeIf { it.isNotBlank() } }
            },
            priceMaxRelDiff = jsonNum(x.optJSONObject("priceValidation"), "maxRelDiff")
        )''',
1,
)

# Sector performance is useful and was already present in Snapshot but had no detail UI.
ds = ds.replace(
'''    val state = f?.status ?: if (isFrozenMainline) "正式主线" else "板块观察"
    val r5 = kReturn(bars, 5);''',
'''    val state = f?.status ?: if (isFrozenMainline) "正式主线" else "板块观察"
    val sectorPerf = snapshot?.sectorPerformance?.get(ref.name)
    val r5 = kReturn(bars, 5);''',
1,
)
ds = ds.replace(
'''            item { DetailSectionTitle("成分股") }''',
'''            item { DetailSectionTitle("后续跟踪") }
            item {
                DetailCard {
                    if (sectorPerf == null || sectorPerf.length() == 0) Text("从正式信号后的下一交易日开盘起算；当前尚未成熟。", color = DetailMuted, fontSize = 10.sp)
                    else {
                        TrackingStrip(sectorPerf)
                        if (snapshot != null && !snapshot.performanceEligible) Text("参考 Tracking · 不进入模型成绩统计", color = DetailMuted, fontSize = 9.sp)
                    }
                }
            }
            item { DetailSectionTitle("成分股") }''',
1,
)

# Replace stock detail with a decision-oriented layout and correct return semantics.
pattern = re.compile(r'@Composable\nfun StockDetailScreen\(code: String, snapshot: Snapshot\?, initialQuote: Quote\?, onBack: \(\) -> Unit\) \{.*?\n\}\n\n@Composable\nprivate fun CandleChart', re.S)
stock_detail = '''@Composable
fun StockDetailScreen(code: String, snapshot: Snapshot?, initialQuote: Quote?, onBack: () -> Unit) {
    var facts by remember(code, snapshot?.date) { mutableStateOf<StockFacts?>(null) }
    var bars by remember(code) { mutableStateOf<List<KBar>>(emptyList()) }
    var quote by remember(code) { mutableStateOf(initialQuote) }
    var loading by remember(code) { mutableStateOf(true) }
    var error by remember(code) { mutableStateOf<String?>(null) }
    val date = DetailNav.stockDate ?: snapshot?.date
    val tail = DetailNav.tailStock?.takeIf { it.code == code }

    LaunchedEffect(code, date) {
        loading = true
        error = null
        facts = date?.let { runCatching { DetailApi.fetchStock(it, code) }.getOrNull() }
        bars = runCatching { DetailApi.fetchKline(stockSecid(code)) }.getOrElse { emptyList() }
        if (quote == null) quote = runCatching { DataApi.fetchQuotes(listOf(symbol(code)))[symbol(code)] }.getOrNull()
        if (facts == null && quote == null && tail == null) error = "该股票不在所选正式批次，且当前行情暂不可用"
        loading = false
    }

    val meta = snapshot?.stocks?.get(code)
    val f = facts
    val name = f?.name ?: meta?.name ?: tail?.name ?: quote?.name ?: code
    val sector = f?.sector ?: meta?.sector ?: tail?.sector
    val pools = when {
        !f?.pools.isNullOrEmpty() -> f!!.pools
        tail?.pools?.isNotEmpty() == true -> tail.pools
        else -> snapshot?.pools?.filterValues { code in it }?.keys?.sorted().orEmpty()
    }
    val signalPrice = f?.selectionPrice ?: meta?.selectionPrice
    val current = quote?.price ?: tail?.price ?: bars.lastOrNull()?.close
    val signalDayMove = quote?.change ?: f?.changePct ?: meta?.dayChangePct ?: tail?.changePct
    val signalPriceReference = if (signalPrice != null && signalPrice > 0 && current != null) (current / signalPrice - 1.0) * 100.0 else null
    val perf = snapshot?.stockPerformance?.get(code)
    val strategyCurrent = jsonReturn(perf?.optJSONObject("current"))
    val entryDate = perf?.optString("entryDate")?.takeIf { it.isNotBlank() }
    val entryPrice = jsonNumber(perf, "entryPrice")
    val mainFlowPct = f?.mainFlowPct ?: meta?.mainFlowPct ?: tail?.mainFlowPct
    val mainFlow = f?.mainNetFlow ?: meta?.mainNetFlow ?: tail?.mainNetFlow
    val amount = f?.amount ?: meta?.amount ?: tail?.amount
    val turnover = f?.turnover ?: meta?.turnover ?: tail?.turnover

    LazyColumn(modifier = Modifier.fillMaxSize().background(DetailBg), contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { DetailBackHeader("个股详情", "$name · $code", onBack) }
        if (loading) item { DetailNotice("正在读取行情、K线、资金和策略跟踪…") }
        error?.let { item { DetailNotice(it) } }

        item {
            DetailCard {
                Row(verticalAlignment = Alignment.Top) {
                    Column(Modifier.weight(1f)) {
                        Text(name, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                        Text("$code · ${sector ?: "未关联正式板块"}", color = DetailMuted, fontSize = 11.sp)
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text(current?.let { String.format("%.2f", it) } ?: "—", fontSize = 22.sp, fontWeight = FontWeight.Bold)
                        Text(signalDayMove?.let { String.format("%+.2f%%", it) } ?: "—", color = if ((signalDayMove ?: 0.0) >= 0) DetailUp else DetailDown, fontSize = 11.sp)
                    }
                }
                if (pools.isNotEmpty()) {
                    Spacer(Modifier.height(8.dp))
                    Text("策略池：${pools.joinToString(" / ") { runCatching { poolTitle(it) }.getOrDefault(it) }}", color = DetailBlue, fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
                }
                Spacer(Modifier.height(8.dp))
                DetailKey("正式信号日", date ?: "—")
                DetailKey("收盘筛选价", signalPrice?.let { String.format("%.2f", it) } ?: "—")
                DetailKey("信号日涨跌", signalDayMove?.let { String.format("%+.2f%%", it) } ?: "—")
                DetailKey("信号价至今参考", signalPriceReference?.let { String.format("%+.2f%%", it) } ?: "—")
                DetailKey("策略 Tracking", strategyCurrent?.let { String.format("%+.2f%%", it * 100.0) } ?: "等待下一交易日可成交开盘")
                DetailKey("置信度", f?.confidence ?: meta?.confidence ?: "—")
            }
        }

        tail?.let { t ->
            item { DetailSectionTitle("尾盘决策身份") }
            item {
                DetailCard {
                    DetailKey("Tail Score", t.tailScore?.let { String.format("%.1f", it) } ?: "—")
                    DetailKey("基础强度", t.baseScore?.let { String.format("%.1f", it) } ?: "—")
                    DetailKey("资金确认分", t.flowScore?.let { String.format("%.1f", it) } ?: "—")
                    DetailKey("尾盘风险", t.risk)
                    DetailKey("可交易", if (t.tailTradable) "是" else "否")
                    DetailKey("Yunai价格核对", when { t.yunaiVerified == true -> "通过"; t.yunaiVerified == false -> "未通过"; else -> "—" })
                    DetailKey("Yunai价格", t.yunaiPrice?.let { String.format("%.2f", it) } ?: "—")
                    DetailKey("Yunai大单净流入(源口径)", t.yunaiLargeNet?.let { String.format("%+.0f", it) } ?: "—")
                    Text("Yunai资金分档与东方财富主力资金口径不同，因此并列展示，不直接混成同一个金额。", color = DetailMuted, fontSize = 9.sp)
                }
            }
        }

        item { DetailExplain("为什么入选", f?.reason ?: meta?.reason ?: tail?.reason ?: "该股票不是当前正式批次的冻结入选股；仍可查看行情与技术趋势。") }

        item { DetailSectionTitle("因子与趋势") }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    DetailMetric("RS20", f?.rs20?.let { String.format("%+.1f%%", it) } ?: meta?.rs?.let { String.format("%+.1f%%", it) } ?: tail?.rs20?.let { String.format("%+.1f%%", it) } ?: "—", Modifier.weight(1f))
                    DetailMetric("RS60", f?.rs60?.let { String.format("%+.1f%%", it) } ?: meta?.rs60?.let { String.format("%+.1f%%", it) } ?: tail?.rs60?.let { String.format("%+.1f%%", it) } ?: "—", Modifier.weight(1f))
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    DetailMetric("MTA多周期", f?.mta ?: meta?.mta ?: tail?.mta ?: "—", Modifier.weight(1f))
                    DetailMetric("综合评分", f?.score?.let { String.format("%.1f", it) } ?: meta?.score?.let { String.format("%.1f", it) } ?: "—", Modifier.weight(1f))
                }
            }
        }

        item { DetailSectionTitle("资金与交易结构") }
        item {
            DetailCard {
                DetailKey("主力净流入", mainFlow?.let(::signedMoney) ?: "—")
                DetailKey("主力资金占比", mainFlowPct?.let { String.format("%+.2f%%", it) } ?: "—")
                DetailKey("成交额", amount?.let(::money) ?: "—")
                DetailKey("换手率", turnover?.let { String.format("%.2f%%", it) } ?: "—")
                DetailKey("B1两融", if ("B1" in pools || "B12" in pools || "B13" in pools) "正式确认" else "尚无正式数据/未达标")
                DetailKey("B2 ETF申赎", if ("B2" in pools || "B12" in pools || "B23" in pools) "正式确认" else "尚无正式数据/未达标")
            }
        }

        item { DetailSectionTitle("K线") }
        item {
            DetailCard {
                if (bars.size < 5) Text("K线数据暂不可用", color = DetailMuted)
                else {
                    CandleChart(bars.takeLast(40))
                    Spacer(Modifier.height(8.dp))
                    DetailKey("5日涨跌", kReturn(bars, 5)?.let { String.format("%+.2f%%", it) } ?: "—")
                    DetailKey("20日涨跌", kReturn(bars, 20)?.let { String.format("%+.2f%%", it) } ?: "—")
                    DetailKey("60日涨跌", kReturn(bars, 60)?.let { String.format("%+.2f%%", it) } ?: "—")
                    DetailKey("距20日高点", distHigh(bars, 20)?.let { String.format("%+.2f%%", it) } ?: "—")
                }
            }
        }

        item { DetailSectionTitle("数据验证") }
        item {
            DetailCard {
                val providers = if (f?.priceProviders?.isNotEmpty() == true) f.priceProviders else meta?.priceProviders.orEmpty()
                val diff = f?.priceMaxRelDiff ?: meta?.priceMaxRelDiff
                DetailKey("收盘价独立源", providers.joinToString(" + ").ifBlank { "—" })
                DetailKey("OHLC最大相对差", diff?.let { String.format("%.3f%%", it * 100.0) } ?: "—")
                DetailKey("规则", if (providers.size >= 2) "至少两独立源未复权OHLC一致" else "待补充验证")
            }
        }

        item { DetailSectionTitle("策略后续收益") }
        item {
            DetailCard {
                DetailKey("入场规则", "信号后下一交易日可成交开盘")
                DetailKey("实际入场日", entryDate ?: "待成熟")
                DetailKey("验证入场价", entryPrice?.let { String.format("%.2f", it) } ?: "—")
                DetailKey("当前 Tracking", strategyCurrent?.let { String.format("%+.2f%%", it * 100.0) } ?: "—")
                Spacer(Modifier.height(8.dp))
                if (perf != null && perf.length() > 0) TrackingStrip(perf) else Text("尚未产生下一交易日可验证入场价，因此不提前填写策略收益。", color = DetailMuted, fontSize = 10.sp)
                Spacer(Modifier.height(8.dp))
                DetailKey("MFE 最大有利涨幅", detailValue(perf, "MFE"))
                DetailKey("MAE 最大不利跌幅", detailValue(perf, "MAE"))
                if (snapshot != null && !snapshot.performanceEligible && perf != null) Text("参考 Tracking：该批次不进入胜率、Alpha或因子成绩统计。", color = DetailMuted, fontSize = 9.sp)
            }
        }
    }
}

@Composable
private fun CandleChart'''
ds, n = pattern.subn(stock_detail, ds, count=1)
if n != 1:
    raise SystemExit('StockDetailScreen replacement failed')

d.write_text(ds, encoding='utf-8')

# ---- Tail panel ----------------------------------------------------------
t = Path('app/src/main/java/com/rui/astockstrategy/v6/TailDecision.kt')
ts = t.read_text(encoding='utf-8')
if 'import androidx.compose.foundation.clickable' not in ts:
    ts = ts.replace('import androidx.compose.foundation.background\n', 'import androidx.compose.foundation.background\nimport androidx.compose.foundation.clickable\n', 1)

# Rich Tail stock fields already present in backend but previously hidden.
pattern = re.compile(r'data class TailStock\(.*?\n\)\n\ndata class TailDecision', re.S)
tail_models = '''data class TailStock(
    val code: String,
    val name: String,
    val sector: String,
    val price: Double?,
    val changePct: Double?,
    val amount: Double?,
    val turnover: Double?,
    val mainNetFlow: Double?,
    val mainFlowPct: Double?,
    val rs20: Double?,
    val rs60: Double?,
    val mta: String?,
    val baseScore: Double?,
    val flowScore: Double?,
    val tailScore: Double?,
    val pools: List<String>,
    val risk: String,
    val tailTradable: Boolean,
    val reason: String?,
    val yunaiVerified: Boolean?,
    val yunaiPrice: Double?,
    val yunaiLargeNet: Double?,
    val yunaiTotalNet: Double?
)

data class TailSector(
    val boardCode: String,
    val name: String,
    val type: String,
    val score: Double?,
    val status: String,
    val changePct: Double?,
    val amount: Double?,
    val mainNetFlow: Double?,
    val mainFlowPct: Double?,
    val breadthPct: Double?,
    val rs20: Double?,
    val rs60: Double?,
    val mta: String?,
    val confidence: String?,
    val reason: String?
)

data class TailDecision'''
ts, n = pattern.subn(tail_models, ts, count=1)
if n != 1:
    raise SystemExit('TailStock model replacement failed')

# Add rich sector arrays while preserving name lists used by existing status text.
ts = ts.replace(
'''    val confirmedMainlines: List<String>,
    val candidateMainlines: List<String>,''',
'''    val confirmedMainlines: List<String>,
    val candidateMainlines: List<String>,
    val confirmedSectors: List<TailSector>,
    val candidateSectors: List<TailSector>,''',
1,
)

# Insert clickable sector cards before stock-pool decision.
needle = '''        if (current.noTrade) {'''
insert = '''        if (current.confirmedSectors.isNotEmpty()) {
            Text("确认主线详情", fontWeight = FontWeight.Bold, fontSize = 14.sp)
            current.confirmedSectors.take(4).forEach { TailSectorRow(it, current.date) }
        } else if (current.candidateSectors.isNotEmpty()) {
            Text("候选板块详情", fontWeight = FontWeight.Bold, fontSize = 14.sp)
            current.candidateSectors.take(4).forEach { TailSectorRow(it, current.date) }
        }

        if (current.noTrade) {'''
if needle not in ts:
    raise SystemExit('Tail sector insertion marker missing')
ts = ts.replace(needle, insert, 1)

ts = ts.replace('current.stocks[code]?.let { TailStockRow(it) }', 'current.stocks[code]?.let { TailStockRow(it, current.date) }')

# Replace tail stock row and add tail sector row.
pattern = re.compile(r'@Composable\nprivate fun TailStockRow\(s: TailStock\) \{.*?\n\}\n\n@Composable\nprivate fun MiniMetric', re.S)
tail_rows = '''@Composable
private fun TailStockRow(s: TailStock, date: String) {
    Card(Modifier.fillMaxWidth().clickable { DetailNav.openTailStock(s, date) }, shape = RoundedCornerShape(14.dp)) {
        Column(Modifier.fillMaxWidth().padding(11.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Row(verticalAlignment = Alignment.Top) {
                Column(Modifier.weight(1f)) {
                    Text(s.name.ifBlank { s.code }, fontWeight = FontWeight.Bold)
                    Text("${s.code} · ${s.sector} · 点开详情", fontSize = 9.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(s.price?.let { String.format("%.2f", it) } ?: "—", fontWeight = FontWeight.Bold)
                    Text(s.changePct?.let { String.format("%+.2f%%", it) } ?: "—", fontSize = 10.sp)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                MiniMetric("尾盘分", s.tailScore?.let { String.format("%.1f", it) } ?: "—", Modifier.weight(1f))
                MiniMetric("主力占比", s.mainFlowPct?.let { String.format("%+.1f%%", it) } ?: "—", Modifier.weight(1f))
                MiniMetric("RS20", s.rs20?.let { String.format("%+.1f%%", it) } ?: "—", Modifier.weight(1f))
            }
            Text("${s.pools.joinToString(" · ")} · ${s.mta ?: "趋势待同步"} · ${s.risk}", fontSize = 9.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            if (s.yunaiVerified != null) Text("Yunai二源价格核对 ${if (s.yunaiVerified) "✓" else "×"} · 资金分档已在详情页并列展示", fontSize = 8.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun TailSectorRow(s: TailSector, date: String) {
    val upApprox = s.breadthPct?.coerceIn(0.0, 100.0)?.toInt() ?: 0
    val board = Board(
        code = s.boardCode,
        name = s.name,
        change = s.changePct,
        amount = s.amount,
        flow = s.mainNetFlow,
        flowPct = s.mainFlowPct,
        up = upApprox,
        down = if (s.breadthPct != null) 100 - upApprox else 0,
        flat = 0,
        type = if (s.type == "概念") "concept" else "industry",
        breadthOverride = s.breadthPct
    )
    Card(Modifier.fillMaxWidth().clickable { DetailNav.openSector(board, date) }, shape = RoundedCornerShape(14.dp)) {
        Column(Modifier.fillMaxWidth().padding(11.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row {
                Column(Modifier.weight(1f)) {
                    Text(s.name, fontWeight = FontWeight.Bold)
                    Text("${s.status} · ${s.type} · 点开趋势/资金/成分股", fontSize = 9.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Text(s.score?.let { String.format("%.1f", it) } ?: "—", fontWeight = FontWeight.Bold)
            }
            Text("涨跌 ${s.changePct?.let { String.format("%+.2f%%", it) } ?: "—"} · 资金占比 ${s.mainFlowPct?.let { String.format("%+.2f%%", it) } ?: "—"} · 广度 ${s.breadthPct?.let { String.format("%.0f%%", it) } ?: "—"}", fontSize = 9.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun MiniMetric'''
ts, n = pattern.subn(tail_rows, ts, count=1)
if n != 1:
    raise SystemExit('TailStockRow replacement failed')

# Replace parser completely (it is the last function in this file).
pattern = re.compile(r'private fun parseTail\(o: JSONObject\): TailDecision \{.*\}\s*$', re.S)
parser = '''private fun parseTail(o: JSONObject): TailDecision {
    fun strings(a: org.json.JSONArray?): List<String> = if (a == null) emptyList() else (0 until a.length()).mapNotNull { i -> a.optString(i).takeIf { it.isNotBlank() } }
    fun names(a: org.json.JSONArray?): List<String> = if (a == null) emptyList() else (0 until a.length()).mapNotNull { i -> a.optJSONObject(i)?.optString("name")?.takeIf { it.isNotBlank() } }
    fun number(x: JSONObject, k: String): Double? = if (!x.has(k) || x.isNull(k)) null else runCatching { x.getDouble(k) }.getOrNull()
    fun sectors(a: org.json.JSONArray?): List<TailSector> = if (a == null) emptyList() else (0 until a.length()).mapNotNull { i ->
        val x = a.optJSONObject(i) ?: return@mapNotNull null
        val name = x.optString("name")
        if (name.isBlank()) return@mapNotNull null
        TailSector(
            boardCode = x.optString("boardCode"), name = name, type = x.optString("type", "板块"),
            score = number(x, "score"), status = x.optString("status", "观察"), changePct = number(x, "changePct"),
            amount = number(x, "amount"), mainNetFlow = number(x, "mainNetFlow"), mainFlowPct = number(x, "mainFlowPct"),
            breadthPct = number(x, "breadthPct"), rs20 = number(x, "RS20"), rs60 = number(x, "RS60"),
            mta = x.optString("MTA").takeIf { it.isNotBlank() }, confidence = x.optString("confidence").takeIf { it.isNotBlank() },
            reason = x.optString("reason").takeIf { it.isNotBlank() }
        )
    }

    val poolsObj = o.optJSONObject("pools") ?: JSONObject()
    val pools = listOf("TB0", "TB3", "TailCore").associateWith { strings(poolsObj.optJSONArray(it)) }
    val stocks = linkedMapOf<String, TailStock>()
    val so = o.optJSONObject("stocks") ?: JSONObject()
    val it = so.keys()
    while (it.hasNext()) {
        val code = it.next()
        val x = so.optJSONObject(code) ?: continue
        val yq = x.optJSONObject("yunaiQuote")
        val yc = x.optJSONObject("yunaiCapital")
        stocks[code] = TailStock(
            code = code,
            name = x.optString("name"),
            sector = x.optString("sector"),
            price = number(x, "price"),
            changePct = number(x, "changePct"),
            amount = number(x, "amount"),
            turnover = number(x, "turnover"),
            mainNetFlow = number(x, "mainNetFlow"),
            mainFlowPct = number(x, "mainFlowPct"),
            rs20 = number(x, "RS20"),
            rs60 = number(x, "RS60"),
            mta = x.optString("MTA").takeIf { it.isNotBlank() },
            baseScore = number(x, "baseScore"),
            flowScore = number(x, "flowScore"),
            tailScore = number(x, "tailScore"),
            pools = strings(x.optJSONArray("pools")),
            risk = x.optString("risk", "—"),
            tailTradable = x.optBoolean("tailTradable", true),
            reason = x.optString("reason").takeIf { it.isNotBlank() },
            yunaiVerified = yq?.let { if (it.has("verifiedWithin1Pct")) it.optBoolean("verifiedWithin1Pct") else null },
            yunaiPrice = yq?.let { number(it, "price") },
            yunaiLargeNet = yc?.let { number(it, "largeNetInflow") },
            yunaiTotalNet = yc?.let { number(it, "totalNetInflow") }
        )
    }
    val confirmedArray = o.optJSONArray("confirmedMainlines")
    val candidateArray = o.optJSONArray("candidateMainlines")
    return TailDecision(
        date = o.optString("date"),
        status = o.optString("status", "TailDecision"),
        phase = o.optString("phase").takeIf { it.isNotBlank() },
        isFinal = o.optBoolean("isFinal", o.optString("status") == "TailFinal"),
        scheduledSlot = o.optString("scheduledSlot").takeIf { it.isNotBlank() },
        refreshIntervalMin = o.optInt("refreshIntervalMin", 5),
        capturedAt = o.optString("capturedAt"),
        boardSource = o.optString("boardSource", "未知"),
        confidence = o.optString("confidence", "—"),
        confirmedMainlines = names(confirmedArray),
        candidateMainlines = names(candidateArray),
        confirmedSectors = sectors(confirmedArray),
        candidateSectors = sectors(candidateArray),
        pools = pools,
        stocks = stocks,
        noTrade = o.optBoolean("noTrade", true)
    )
}
'''
ts, n = pattern.subn(parser, ts, count=1)
if n != 1:
    raise SystemExit('parseTail replacement failed')

t.write_text(ts, encoding='utf-8')

# v2.0 after v1.9 returns UI.
g = Path('app/build.gradle.kts')
gs = g.read_text(encoding='utf-8')
gs = gs.replace('versionCode = 20', 'versionCode = 21')
gs = gs.replace('versionName = "1.9.0"', 'versionName = "2.0.0"')
g.write_text(gs, encoding='utf-8')
