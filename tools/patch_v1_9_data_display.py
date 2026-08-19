from pathlib import Path
import re


def replace_between(text: str, start: str, end: str, replacement: str) -> str:
    a = text.find(start)
    if a < 0:
        raise SystemExit(f'start marker not found: {start[:80]}')
    b = text.find(end, a + len(start))
    if b < 0:
        raise SystemExit(f'end marker not found: {end[:80]}')
    return text[:a] + replacement.rstrip() + "\n\n" + text[b:]


# -----------------------------------------------------------------------------
# Main app: parse every strategy field that is already present in snapshots and
# make Official / pool / history screens show data instead of silent blanks.
# -----------------------------------------------------------------------------
p = Path('app/src/main/java/com/rui/astockstrategy/v6/V6Activity.kt')
s = p.read_text(encoding='utf-8')

# Rich formal-sector model.
if 'data class OfficialSector(' not in s:
    marker = 'data class StockMeta(\n'
    block = '''data class OfficialSector(\n    val code: String,\n    val name: String,\n    val type: String?,\n    val score: Double?,\n    val status: String?,\n    val changePct: Double?,\n    val amount: Double?,\n    val mainNetFlow: Double?,\n    val mainFlowPct: Double?,\n    val breadthPct: Double?,\n    val rs20: Double?,\n    val rs60: Double?,\n    val mta: String?,\n    val confidence: String?,\n    val reason: String?\n)\n\n'''
    if marker not in s:
        raise SystemExit('StockMeta marker missing')
    s = s.replace(marker, block + marker, 1)

# Extend StockMeta with data already present in the backend JSON.
old = '''data class StockMeta(\n    val code: String,\n    val name: String?,\n    val sector: String?,\n    val rs: Double?,\n    val mta: String?,\n    val score: Double?,\n    val reason: String?,\n    val selectionPrice: Double?,\n    val confidence: String?\n)'''
new = '''data class StockMeta(\n    val code: String,\n    val name: String?,\n    val sector: String?,\n    val rs: Double?,\n    val mta: String?,\n    val score: Double?,\n    val reason: String?,\n    val selectionPrice: Double?,\n    val confidence: String?,\n    val dayChangePct: Double?,\n    val amount: Double?,\n    val turnover: Double?,\n    val mainNetFlow: Double?,\n    val mainFlowPct: Double?,\n    val rs60: Double?,\n    val priceProviders: List<String>,\n    val priceMaxRelDiff: Double?\n)'''
if old in s:
    s = s.replace(old, new, 1)
elif 'val dayChangePct: Double?' not in s:
    raise SystemExit('unexpected StockMeta shape')

# Snapshot has already been extended by the audit patch at this point.
if 'val selectedSectors: List<OfficialSector>' not in s:
    s = s.replace(
        '    val auditIssues: List<String>,\n    val mainlines: List<String>,',
        '    val auditIssues: List<String>,\n    val selectedSectors: List<OfficialSector>,\n    val factorAvailability: Map<String, String>,\n    val trackingUse: String?,\n    val mainlines: List<String>,',
        1,
    )

# Replace StockMeta parser with named parameters + complete fields.
pattern = re.compile(r'''\s*stocks\[code\] = StockMeta\(\n\s*code,\n\s*x\.optString\("name"\).*?\n\s*\)''', re.S)
m = pattern.search(s)
if not m:
    raise SystemExit('StockMeta parser block not found')
parser = '''\n                val pv = x.optJSONObject("priceValidation")\n                stocks[code] = StockMeta(\n                    code = code,\n                    name = x.optString("name").takeIf { it.isNotBlank() },\n                    sector = x.optString("sector").takeIf { it.isNotBlank() },\n                    rs = num(x, "RS") ?: num(x, "rs"),\n                    mta = x.optString("MTA").takeIf { it.isNotBlank() } ?: x.optString("mta").takeIf { it.isNotBlank() },\n                    score = num(x, "score"),\n                    reason = x.optString("reason").takeIf { it.isNotBlank() },\n                    selectionPrice = num(x, "selectionPrice"),\n                    confidence = x.optString("confidence").takeIf { it.isNotBlank() },\n                    dayChangePct = num(x, "changePct"),\n                    amount = num(x, "amount"),\n                    turnover = num(x, "turnover"),\n                    mainNetFlow = num(x, "mainNetFlow"),\n                    mainFlowPct = num(x, "mainFlowPct"),\n                    rs60 = num(x, "RS60") ?: num(x, "rs60"),\n                    priceProviders = arrStrings(pv?.optJSONArray("providers")),\n                    priceMaxRelDiff = pv?.let { num(it, "maxRelDiff") }\n                )'''
s = s[:m.start()] + parser + s[m.end():]

# Parse selectedSectors / factorAvailability / tracking display classification.
audit_marker = '        val audit = o.optJSONObject("audit")\n'
if audit_marker not in s:
    raise SystemExit('audit parser marker missing')
if 'val selectedSectors = parseOfficialSectors' not in s:
    s = s.replace(
        audit_marker,
        '''        val selectedSectors = parseOfficialSectors(o.optJSONArray("selectedSectors"))\n        val factorAvailability = stringMap(o.optJSONObject("factorAvailability"))\n        val trackingUse = o.optString("trackingUse").takeIf { it.isNotBlank() }\n            ?: o.optString("trackingDisplayStatus").takeIf { it.isNotBlank() }\n''' + audit_marker,
        1,
    )

constructor_marker = '''            auditIssues = auditIssues,\n            mainlines = arrStrings(o.optJSONArray("mainlines")),'''
if constructor_marker in s:
    s = s.replace(
        constructor_marker,
        '''            auditIssues = auditIssues,\n            selectedSectors = selectedSectors,\n            factorAvailability = factorAvailability,\n            trackingUse = trackingUse,\n            mainlines = arrStrings(o.optJSONArray("mainlines")),''',
        1,
    )
elif 'selectedSectors = selectedSectors' not in s:
    raise SystemExit('Snapshot constructor marker missing')

# Helpers inside DataApi.
helper_marker = '''    private fun arrStrings(a: JSONArray?): List<String> {'''
if 'private fun parseOfficialSectors' not in s:
    helper = '''    private fun parseOfficialSectors(a: JSONArray?): List<OfficialSector> {\n        if (a == null) return emptyList()\n        return (0 until a.length()).mapNotNull { i ->\n            val x = a.optJSONObject(i) ?: return@mapNotNull null\n            val name = x.optString("name").takeIf { it.isNotBlank() } ?: return@mapNotNull null\n            OfficialSector(\n                code = x.optString("boardCode", x.optString("code")),\n                name = name,\n                type = x.optString("type").takeIf { it.isNotBlank() },\n                score = num(x, "score"),\n                status = x.optString("status").takeIf { it.isNotBlank() },\n                changePct = num(x, "changePct"),\n                amount = num(x, "amount"),\n                mainNetFlow = num(x, "mainNetFlow"),\n                mainFlowPct = num(x, "mainFlowPct"),\n                breadthPct = num(x, "breadthPct"),\n                rs20 = num(x, "RS20"),\n                rs60 = num(x, "RS60"),\n                mta = x.optString("MTA").takeIf { it.isNotBlank() },\n                confidence = x.optString("confidence").takeIf { it.isNotBlank() },\n                reason = x.optString("reason").takeIf { it.isNotBlank() }\n            )\n        }\n    }\n\n    private fun stringMap(o: JSONObject?): Map<String, String> {\n        if (o == null) return emptyMap()\n        val out = linkedMapOf<String, String>()\n        val it = o.keys()\n        while (it.hasNext()) {\n            val k = it.next()\n            val v = o.opt(k)\n            if (v != null && v != JSONObject.NULL) out[k] = v.toString()\n        }\n        return out\n    }\n\n'''
    if helper_marker not in s:
        raise SystemExit('arrStrings helper marker missing')
    s = s.replace(helper_marker, helper + helper_marker, 1)

# Replace main top-level screens so current data is never hidden behind an empty mainlines array.
today = r'''@Composable
fun TodayScreen(
    s: Snapshot?,
    preview: List<PreviewSector>,
    quotes: Map<String, Quote>,
    now: Long,
    quoteOkAt: Long,
    boardOkAt: Long
) {
    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { StatusCard(now, quoteOkAt, boardOkAt, s) }
        item { TailDecisionPanel() }

        if (!marketOpenNow()) {
            item { PostCloseDashboard(quotes, preview, s) }
        } else {
            item { Title("盘中主线预览") }
            item { Notice("盘中预览每30秒随实时板块行情变化；正式股票池只在收盘数据通过验证后冻结。") }
            if (preview.isEmpty()) item { EmptyCard("等待实时板块数据") }
            else items(preview.take(5)) { PreviewRow(it) }
        }

        item { Title("最新正式策略") }
        if (s == null) {
            item { EmptyCard("正式策略尚未同步；行情和尾盘池仍可独立查看") }
        } else {
            item {
                CardBlock {
                    Key("日期", s.date)
                    Key("状态", snapshotAuditLabel(s))
                    Key("市场状态", s.regime)
                    Key("确认主线", s.mainlines.joinToString(" / ").ifBlank { "无" })
                    Key("正式候选板块", s.selectedSectors.take(4).joinToString(" / ") { it.name }.ifBlank { "无" })
                    Key("B0 / B3 / B4", "${s.pools["B0"].orEmpty().size} / ${s.pools["B3"].orEmpty().size} / ${s.pools["B4"].orEmpty().size} 只")
                }
            }
            item { DataCoverageCard(s) }
            if (!s.performanceEligible) item { AuditWarning(s) }

            if (s.selectedSectors.isNotEmpty()) {
                item { Title("收盘正式候选板块") }
                items(s.selectedSectors.take(6)) { OfficialSectorRow(it, s.date) }
            }

            val b4 = s.pools["B4"].orEmpty()
            val fallback = if (b4.isNotEmpty()) b4 else (s.pools["B0"].orEmpty() + s.pools["B3"].orEmpty()).distinct()
            item { Title(if (b4.isNotEmpty()) "B4 综合确认池" else "正式股票候选") }
            item { SameDayPoolCard(s, if (b4.isNotEmpty()) "B4" else "B0") }
            if (fallback.isEmpty()) item { EmptyCard("今日没有达标股票") }
            else items(fallback.take(10)) { code -> StockLiveRow(code, s, quotes[symbol(code)]) }
        }
    }
}'''
s = replace_between(s, '@Composable\nfun TodayScreen(', '@Composable\nfun StatusCard(', today)

mainline = r'''@Composable
fun MainlineScreen(s: Snapshot?, preview: List<PreviewSector>, now: Long, boardOkAt: Long) {
    var mode by remember { mutableStateOf("盘中Preview") }
    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { Choice(listOf("盘中Preview", "Official"), mode) { mode = it } }
        if (mode == "盘中Preview") {
            item { Notice("实时主线候选每30秒重算；点任意板块可查看趋势、资金、广度和成分股。") }
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
}'''
s = replace_between(s, '@Composable\nfun MainlineScreen(', '@Composable\nfun PoolsScreen(', mainline)

pools = r'''@Composable
fun PoolsScreen(s: Snapshot?, quotes: Map<String, Quote>, now: Long, quoteOkAt: Long) {
    if (s == null) { Empty("暂无正式股票池快照"); return }
    var pool by remember(s.date) { mutableStateOf("B4") }
    val codes = s.pools[pool].orEmpty()
    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
        item { PoolSelector(pool) { pool = it } }
        item { Notice("${poolTitle(pool)} 来自 ${s.date} 的 ${snapshotAuditLabel(s)}；名单冻结，行情独立更新。点个股进入完整详情。") }
        item { SameDayPoolCard(s, pool) }
        item { LiveBadge("行情", freshnessLabel(now, quoteOkAt, 15000, "实时", "已过期"), marketStateOk(now, quoteOkAt), Modifier.fillMaxWidth()) }
        if (codes.isEmpty()) item { EmptyCard("${poolTitle(pool)} 当前为空；必要因子缺失或没有共同达标股票时不会补假信号。") }
        else items(codes) { code -> StockLiveRow(code, s, quotes[symbol(code)]) }
        item { ForwardTrackingCard(s, pool) }
    }
}'''
s = replace_between(s, '@Composable\nfun PoolsScreen(', '@Composable\nfun HistoryScreen(', pools)

history = r'''@Composable
fun HistoryScreen(
    all: List<Snapshot>,
    s: Snapshot?,
    quotes: Map<String, Quote>,
    selectedDate: String?,
    onDate: (String) -> Unit
) {
    if (all.isEmpty()) { Empty("历史数据库为空"); return }
    val sorted = all.sortedByDescending { it.date }
    var pool by remember(s?.date) { mutableStateOf("B4") }
    val snap = s ?: sorted.first()
    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { Title("历史时间机器") }
        item { Notice("信号日行情、冻结名单和次日开盘起的 Forward Tracking 分开显示。历史详情的K线严格截止所选日期。") }
        items(sorted.take(40).chunked(4)) { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                row.forEach { item -> DateChip(item, selectedDate == item.date || (selectedDate == null && item.date == snap.date), Modifier.weight(1f)) { onDate(item.date) } }
                repeat(4 - row.size) { Spacer(Modifier.weight(1f)) }
            }
        }
        item { CardBlock { Key("日期", snap.date); Key("状态", snapshotAuditLabel(snap)); Key("市场状态", snap.regime); Key("确认主线", snap.mainlines.joinToString(" / ").ifBlank { "无" }); Key("正式候选", snap.selectedSectors.take(4).joinToString(" / ") { it.name }.ifBlank { "无" }) } }
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
}'''
s = replace_between(s, '@Composable\nfun HistoryScreen(', '@Composable\nfun PreviewRow(', history)

stock_row = r'''@Composable
fun StockLiveRow(code: String, s: Snapshot, q: Quote?) {
    val meta = s.stocks[code]
    val perf = s.stockPerformance[code]
    val displayPrice = q?.price ?: meta?.selectionPrice
    val dayMove = q?.change ?: meta?.dayChangePct
    val selection = meta?.selectionPrice
    val liveReturn = if (selection != null && selection > 0 && q?.price != null) (q.price / selection - 1.0) * 100.0 else null
    Card(Modifier.fillMaxWidth().clickable { DetailNav.openStock(code, s.date) }, shape = RoundedCornerShape(15.dp)) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Row {
                Column(Modifier.weight(1f)) {
                    Text(meta?.name ?: q?.name ?: code, fontWeight = FontWeight.Bold)
                    Text("$code · ${meta?.sector ?: "未分类"} · 点开详情", fontSize = 10.sp, color = Muted)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(displayPrice?.let { String.format("%.2f", it) } ?: "数据未同步", fontWeight = FontWeight.Bold)
                    Text(dayMove?.let(::pct) ?: "当日涨跌未同步", color = dayMove?.let(::pnl) ?: Muted, fontSize = 11.sp)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                Text("入池收盘 ${selection?.let { String.format("%.2f", it) } ?: "未同步"}", fontSize = 9.sp, color = Muted)
                Text("收盘后变化 ${liveReturn?.let { String.format("%+.2f%%", it) } ?: "待下一行情"}", fontSize = 9.sp, color = liveReturn?.let(::pnl) ?: Muted)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                Text("主力 ${meta?.mainNetFlow?.let(::signedMoney) ?: "未同步"}", fontSize = 9.sp, color = Muted)
                Text("换手 ${meta?.turnover?.let { String.format("%.2f%%", it) } ?: "未同步"}", fontSize = 9.sp, color = Muted)
            }
            if (perf != null && perf.length() > 0) Text("策略跟踪 ${detailCurrentReturn(perf)} · ${if (s.performanceEligible) "已纳入统计" else "参考展示"}", fontSize = 9.sp, color = Blue)
        }
    }
}'''
s = replace_between(s, '@Composable\nfun StockLiveRow(', '@Composable\nfun HistoryStockRow(', stock_row)

history_row = r'''@Composable
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
                Text("当前跟踪 ${detailCurrentReturn(perf)}${if (!s.performanceEligible) " · 参考，不计入策略统计" else ""}", fontSize = 9.sp, color = if (s.performanceEligible) Blue else Amber)
            } else {
                Text(if (s.date == LocalDate.now(CnZone).toString()) "策略收益从下一交易日开盘开始，今天尚未产生" else "Forward Tracking 尚未同步", fontSize = 9.sp, color = Muted)
            }
        }
    }
}'''
s = replace_between(s, '@Composable\nfun HistoryStockRow(', '@Composable\nfun IndexCard(', history_row)

# App-level display helpers inserted before Choice.
choice_marker = '@Composable\nfun Choice(items: List<String>, value: String, onChange: (String) -> Unit) {'
if 'fun OfficialSectorRow(' not in s:
    helpers = r'''@Composable
fun OfficialSectorRow(x: OfficialSector, date: String) {
    Surface(Modifier.fillMaxWidth().clickable { DetailNav.openSectorName(x.name, date) }, color = Color.White, shape = RoundedCornerShape(16.dp)) {
        Column(Modifier.fillMaxWidth().padding(13.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Row {
                Column(Modifier.weight(1f)) {
                    Text(x.name, fontWeight = FontWeight.Bold)
                    Text("${x.type ?: "板块"} · ${x.status ?: "候选"} · 点开详情", fontSize = 9.sp, color = Muted)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(x.changePct?.let(::pct) ?: "涨跌未同步", color = x.changePct?.let(::pnl) ?: Muted, fontWeight = FontWeight.Bold)
                    Text(x.score?.let { "Score ${String.format("%.1f", it)}" } ?: "评分未同步", fontSize = 9.sp, color = Muted)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                Text("广度 ${x.breadthPct?.let { String.format("%.0f%%", it) } ?: "未同步"}", fontSize = 9.sp, color = Muted)
                Text("主力 ${x.mainNetFlow?.let(::signedMoney) ?: "未同步"}", fontSize = 9.sp, color = Muted)
            }
            if (!x.mta.isNullOrBlank()) Text("${x.mta} · 置信度 ${x.confidence ?: "未标注"}", fontSize = 9.sp, color = Blue)
        }
    }
}

@Composable
fun OfficialMainlineFallback(name: String, date: String) {
    Surface(Modifier.fillMaxWidth().clickable { DetailNav.openSectorName(name, date) }, color = Color.White, shape = RoundedCornerShape(16.dp)) {
        Column(Modifier.fillMaxWidth().padding(13.dp)) {
            Text(name, fontWeight = FontWeight.Bold)
            Text("确认主线 · $date · 点开详情", fontSize = 9.sp, color = Muted)
        }
    }
}

private fun poolDayValues(s: Snapshot, pool: String): List<Double> = s.pools[pool].orEmpty().mapNotNull { s.stocks[it]?.dayChangePct }

@Composable
fun SameDayPoolCard(s: Snapshot, pool: String) {
    val values = poolDayValues(s, pool)
    CardBlock {
        Text("信号日行情（不是策略收益）", fontWeight = FontWeight.Bold)
        if (values.isEmpty()) {
            Text("当日涨跌字段尚未同步", color = Muted, fontSize = 11.sp)
        } else {
            Key("池内平均涨跌", String.format("%+.2f%%", values.average()))
            Key("上涨占比", String.format("%.0f%%", values.count { it > 0 }.toDouble() / values.size * 100.0))
            Key("有数据股票", "${values.size}/${s.pools[pool].orEmpty().size}")
            Text("这反映信号形成当天已经发生的行情，不作为从入池后开始计算的策略收益。", fontSize = 9.sp, color = Muted)
        }
    }
}

@Composable
fun ForwardTrackingCard(s: Snapshot, pool: String) {
    val perf = s.poolPerformance[pool]
    CardBlock {
        Text("次一交易日开盘起 Forward Tracking", fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(6.dp))
        if (perf == null || perf.length() == 0) {
            Text(if (s.date == LocalDate.now(CnZone).toString()) "今天收盘刚形成信号；策略收益从下一交易日可成交开盘开始。" else "跟踪数据尚未同步", color = Muted, fontSize = 11.sp)
        } else {
            TrackingStrip(perf)
            Spacer(Modifier.height(5.dp))
            Text("当前 ${detailCurrentReturn(perf)}${if (!s.performanceEligible || s.trackingUse == "ReferenceOnly") " · 参考展示，不计入模型统计" else " · 已通过审计，可计入统计"}", fontSize = 9.sp, color = if (s.performanceEligible) Blue else Amber)
        }
    }
}

fun detailCurrentReturn(p: JSONObject?): String {
    if (p == null) return "—"
    val cur = p.optJSONObject("current") ?: return "—"
    val r = cur.opt("return")
    return if (r == null || r == JSONObject.NULL) "—" else pretty(r)
}

@Composable
fun DataCoverageCard(s: Snapshot) {
    val allCodes = s.pools.values.flatten().distinct()
    val metas = allCodes.mapNotNull { s.stocks[it] }
    fun count(selector: (StockMeta) -> Boolean) = metas.count(selector)
    CardBlock {
        Text("数据完整性", fontWeight = FontWeight.Bold)
        Key("正式候选板块", "${s.selectedSectors.size}")
        Key("股票元数据", "${metas.size}/${allCodes.size}")
        Key("当日涨跌", "${count { it.dayChangePct != null }}/${allCodes.size}")
        Key("已验证入池价", "${count { it.selectionPrice != null && it.priceProviders.size >= 2 }}/${allCodes.size}")
        Key("主力资金", "${count { it.mainNetFlow != null }}/${allCodes.size}")
        Key("Forward Tracking", "${s.stockPerformance.size}/${allCodes.size}")
        val missing = s.factorAvailability.filterValues { it.contains("未同步") || it.contains("留空") }
        if (missing.isNotEmpty()) Text(missing.entries.joinToString(" · ") { "${it.key}: ${it.value}" }, fontSize = 8.sp, color = Amber, maxLines = 4)
    }
}

'''
    if choice_marker not in s:
        raise SystemExit('Choice marker missing')
    s = s.replace(choice_marker, helpers + choice_marker, 1)

p.write_text(s, encoding='utf-8')

# -----------------------------------------------------------------------------
# Post-close board cards: clickable.
# -----------------------------------------------------------------------------
pc = Path('app/src/main/java/com/rui/astockstrategy/v6/PostCloseDashboard.kt')
ps = pc.read_text(encoding='utf-8')
if 'import androidx.compose.foundation.clickable' not in ps:
    ps = ps.replace('package com.rui.astockstrategy.v6\n', 'package com.rui.astockstrategy.v6\n\nimport androidx.compose.foundation.clickable\n', 1)
ps = ps.replace(
    'Card(Modifier.fillMaxWidth(), shape = RoundedCornerShape(14.dp)) {',
    'Card(Modifier.fillMaxWidth().clickable { DetailNav.openSector(p.board) }, shape = RoundedCornerShape(14.dp)) {',
)
ps = ps.replace('Text("${p.state} · 上涨扩散度 ${String.format("%.0f%%", p.breadth)}", fontSize = 10.sp)', 'Text("${p.state} · 上涨扩散度 ${String.format("%.0f%%", p.breadth)} · 点开详情", fontSize = 10.sp)')
pc.write_text(ps, encoding='utf-8')

# -----------------------------------------------------------------------------
# Historical heatmap cards: clickable and date-aware.
# -----------------------------------------------------------------------------
h = Path('app/src/main/java/com/rui/astockstrategy/v6/HistoricalReplay.kt')
hs = h.read_text(encoding='utf-8')
if 'import androidx.compose.foundation.clickable' not in hs:
    hs = hs.replace('import androidx.compose.foundation.background\n', 'import androidx.compose.foundation.background\nimport androidx.compose.foundation.clickable\n', 1)
hs = hs.replace('mode == "行业热力" -> HistHeatmap(data!!.industry, "行业")', 'mode == "行业热力" -> HistHeatmap(data!!.industry, "行业", data!!.date)')
hs = hs.replace('else -> HistHeatmap(data!!.concept, "概念")', 'else -> HistHeatmap(data!!.concept, "概念", data!!.date)')
hs = hs.replace('private fun HistHeatmap(items: List<HistBoard>, title: String) {', 'private fun HistHeatmap(items: List<HistBoard>, title: String, date: String) {')
hs = hs.replace('pair.forEach { b -> HistHeatTile(b, Modifier.weight(1f)) }', 'pair.forEach { b -> HistHeatTile(b, date, Modifier.weight(1f)) }')
hs = hs.replace('private fun HistHeatTile(b: HistBoard, modifier: Modifier) {', 'private fun HistHeatTile(b: HistBoard, date: String, modifier: Modifier) {')
hs = hs.replace('Card(modifier, colors = CardDefaults.cardColors(containerColor = bg), shape = RoundedCornerShape(14.dp)) {', 'Card(modifier.clickable { DetailNav.openSectorName(b.name, date) }, colors = CardDefaults.cardColors(containerColor = bg), shape = RoundedCornerShape(14.dp)) {')
hs = hs.replace('Text(b.mainNetFlow?.let { "资金 ${histSignedMoney(it)}" } ?: "资金 —", fontSize = 8.sp, color = HistMuted, maxLines = 1)', 'Text(b.mainNetFlow?.let { "资金 ${histSignedMoney(it)} · 点开详情" } ?: "资金未同步 · 点开详情", fontSize = 8.sp, color = HistMuted, maxLines = 1)')
h.write_text(hs, encoding='utf-8')

# -----------------------------------------------------------------------------
# Tail pool: parse/display the Yunai overlay and allow TailCore drill-down.
# -----------------------------------------------------------------------------
t = Path('app/src/main/java/com/rui/astockstrategy/v6/TailDecision.kt')
ts = t.read_text(encoding='utf-8')
if 'import androidx.compose.foundation.clickable' not in ts:
    ts = ts.replace('import androidx.compose.foundation.background\n', 'import androidx.compose.foundation.background\nimport androidx.compose.foundation.clickable\n', 1)
old_tail_model = '''    val pools: List<String>,\n    val risk: String\n)'''
new_tail_model = '''    val pools: List<String>,\n    val risk: String,\n    val amount: Double?,\n    val turnover: Double?,\n    val mainNetFlow: Double?,\n    val reason: String?,\n    val yunaiVerified: Boolean?,\n    val yunaiPrice: Double?,\n    val yunaiLargeNetInflow: Double?,\n    val yunaiTotalNetInflow: Double?\n)'''
if old_tail_model in ts:
    ts = ts.replace(old_tail_model, new_tail_model, 1)
ts = ts.replace('current.stocks[code]?.let { TailStockRow(it) }', 'current.stocks[code]?.let { TailStockRow(it, current.date) }')
ts = ts.replace('private fun TailStockRow(s: TailStock) {\n    Card(shape = RoundedCornerShape(14.dp)) {', 'private fun TailStockRow(s: TailStock, date: String) {\n    Card(Modifier.fillMaxWidth().clickable { DetailNav.openTailStock(s, date) }, shape = RoundedCornerShape(14.dp)) {')
ts = ts.replace('Text("${s.code} · ${s.sector}", fontSize = 9.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)', 'Text("${s.code} · ${s.sector} · 点开详情", fontSize = 9.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)')
ts = ts.replace('Text("${s.pools.joinToString(" · ")} · ${s.mta ?: "趋势待同步"} · ${s.risk}", fontSize = 9.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)', 'Text("${s.pools.joinToString(" · ")} · ${s.mta ?: "趋势待同步"} · ${s.risk}", fontSize = 9.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)\n            Text("Yunai ${if (s.yunaiVerified == true) "行情已核对" else "核对未确认"} · 大单 ${s.yunaiLargeNetInflow?.let { String.format("%+.0f", it) } ?: "未同步"}", fontSize = 8.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)')
# Tail parser constructor: append fields before closing.
old_ctor = '''            pools = strings(x.optJSONArray("pools")),\n            risk = x.optString("risk", "—")\n        )'''
new_ctor = '''            pools = strings(x.optJSONArray("pools")),\n            risk = x.optString("risk", "—"),\n            amount = number(x, "amount"),\n            turnover = number(x, "turnover"),\n            mainNetFlow = number(x, "mainNetFlow"),\n            reason = x.optString("reason").takeIf { it.isNotBlank() },\n            yunaiVerified = x.optJSONObject("yunaiQuote")?.let { if (it.has("verifiedWithin1Pct")) it.optBoolean("verifiedWithin1Pct") else null },\n            yunaiPrice = x.optJSONObject("yunaiQuote")?.let { number(it, "price") },\n            yunaiLargeNetInflow = x.optJSONObject("yunaiCapital")?.let { number(it, "largeNetInflow") },\n            yunaiTotalNetInflow = x.optJSONObject("yunaiCapital")?.let { number(it, "totalNetInflow") }\n        )'''
if old_ctor in ts:
    ts = ts.replace(old_ctor, new_ctor, 1)
t.write_text(ts, encoding='utf-8')

# -----------------------------------------------------------------------------
# Detail pages: Tail context, historical cutoff, verified-price provenance and a
# clear separation between signal-day move and forward strategy return.
# -----------------------------------------------------------------------------
d = Path('app/src/main/java/com/rui/astockstrategy/v6/DetailScreens.kt')
ds = d.read_text(encoding='utf-8')
if 'import java.time.LocalDate' not in ds:
    ds = ds.replace('import java.net.URLEncoder\n', 'import java.net.URLEncoder\nimport java.time.LocalDate\nimport java.time.ZoneId\n', 1)

# Tail navigation context.
if 'var tailStock by mutableStateOf<TailStock?>' not in ds:
    ds = ds.replace('    var stockDate by mutableStateOf<String?>(null)\n', '    var stockDate by mutableStateOf<String?>(null)\n    var tailStock by mutableStateOf<TailStock?>(null)\n', 1)
    ds = ds.replace('        stockDate = null\n    }\n\n    fun openSectorName', '        stockDate = null\n        tailStock = null\n    }\n\n    fun openSectorName', 1)
    # openSectorName also clears tail context.
    ds = ds.replace('        stockDate = null\n    }\n\n    fun openStock(code: String, date: String?) {\n        stockCode = code\n        stockDate = date\n    }', '        stockDate = null\n        tailStock = null\n    }\n\n    fun openStock(code: String, date: String?) {\n        stockCode = code\n        stockDate = date\n        tailStock = null\n    }\n\n    fun openTailStock(stock: TailStock, date: String?) {\n        stockCode = stock.code\n        stockDate = date\n        tailStock = stock\n    }', 1)
    ds = ds.replace('            stockDate = null\n        } else {', '            stockDate = null\n            tailStock = null\n        } else {', 1)
    ds = ds.replace('        stockDate = null\n    }\n}', '        stockDate = null\n        tailStock = null\n    }\n}', 1)

# Price provenance in StockFacts.
old_sf = '''    val mainFlowPct: Double?,\n    val pools: List<String>\n)'''
new_sf = '''    val mainFlowPct: Double?,\n    val pools: List<String>,\n    val priceProviders: List<String>,\n    val priceMaxRelDiff: Double?\n)'''
if old_sf in ds:
    ds = ds.replace(old_sf, new_sf, 1)

# Date-aware K line API.
ds = ds.replace('suspend fun fetchKline(secid: String, limit: Int = 90): List<KBar> = withContext(Dispatchers.IO) {\n        val query = "secid=${enc(secid)}&klt=101&fqt=1&lmt=$limit&end=20500101', 'suspend fun fetchKline(secid: String, limit: Int = 90, endDate: String? = null): List<KBar> = withContext(Dispatchers.IO) {\n        val end = endDate?.replace("-", "") ?: "20500101"\n        val query = "secid=${enc(secid)}&klt=101&fqt=1&lmt=$limit&end=$end')

# StockFacts parser: attach price validation.
old_sf_ctor = '''            mainFlowPct = jsonNum(x, "mainFlowPct"),\n            pools = ps.distinct().sorted()\n        )'''
new_sf_ctor = '''            mainFlowPct = jsonNum(x, "mainFlowPct"),\n            pools = ps.distinct().sorted(),\n            priceProviders = run {\n                val a = x.optJSONObject("priceValidation")?.optJSONArray("providers")\n                if (a == null) emptyList() else (0 until a.length()).mapNotNull { i -> a.optString(i).takeIf { it.isNotBlank() } }\n            },\n            priceMaxRelDiff = jsonNum(x.optJSONObject("priceValidation"), "maxRelDiff")\n        )'''
if old_sf_ctor in ds:
    ds = ds.replace(old_sf_ctor, new_sf_ctor, 1)

# Sector Kline cutoff.
ds = ds.replace('bars = runCatching { DetailApi.fetchKline(boardSecid(code)) }.getOrElse { emptyList() }', 'bars = runCatching { DetailApi.fetchKline(boardSecid(code), 90, historicalDate) }.getOrElse { emptyList() }')

stock_detail = r'''@Composable
fun StockDetailScreen(code: String, snapshot: Snapshot?, initialQuote: Quote?, onBack: () -> Unit) {
    var facts by remember(code, snapshot?.date) { mutableStateOf<StockFacts?>(null) }
    var bars by remember(code, snapshot?.date) { mutableStateOf<List<KBar>>(emptyList()) }
    var quote by remember(code) { mutableStateOf(initialQuote) }
    var loading by remember(code) { mutableStateOf(true) }
    var error by remember(code) { mutableStateOf<String?>(null) }
    val date = DetailNav.stockDate ?: snapshot?.date
    val tail = DetailNav.tailStock?.takeIf { it.code == code }
    val today = LocalDate.now(ZoneId.of("Asia/Shanghai")).toString()
    val historical = date != null && date < today

    LaunchedEffect(code, date) {
        loading = true
        error = null
        facts = date?.let { runCatching { DetailApi.fetchStock(it, code) }.getOrNull() }
        bars = runCatching { DetailApi.fetchKline(stockSecid(code), 90, date) }.getOrElse { emptyList() }
        if (!historical && quote == null) quote = runCatching { DataApi.fetchQuotes(listOf(symbol(code)))[symbol(code)] }.getOrNull()
        if (facts == null && quote == null && tail == null && bars.isEmpty()) error = "该股票的策略元数据和行情均暂不可用"
        loading = false
    }

    val meta = snapshot?.stocks?.get(code)
    val f = facts
    val name = f?.name ?: meta?.name ?: tail?.name ?: quote?.name ?: code
    val sector = f?.sector ?: meta?.sector ?: tail?.sector
    val pools = if (!f?.pools.isNullOrEmpty()) f!!.pools else snapshot?.pools?.filterValues { code in it }?.keys?.sorted().orEmpty()
    val selection = f?.selectionPrice ?: meta?.selectionPrice
    val displayPrice = if (historical) bars.lastOrNull()?.close ?: selection else quote?.price ?: bars.lastOrNull()?.close ?: selection
    val signalDayMove = f?.changePct ?: meta?.dayChangePct ?: tail?.changePct
    val perf = snapshot?.stockPerformance?.get(code)
    val providers = if (!f?.priceProviders.isNullOrEmpty()) f!!.priceProviders else meta?.priceProviders.orEmpty()
    val maxDiff = f?.priceMaxRelDiff ?: meta?.priceMaxRelDiff

    LazyColumn(modifier = Modifier.fillMaxSize().background(DetailBg), contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { DetailBackHeader("个股详情", "$name · $code", onBack) }
        if (loading) item { DetailNotice("正在读取行情、策略因子、K线和跟踪数据…") }
        error?.let { item { DetailNotice(it) } }

        item {
            DetailCard {
                Row(verticalAlignment = Alignment.Top) {
                    Column(Modifier.weight(1f)) {
                        Text(name, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                        Text("$code · ${sector ?: "未关联板块"}", color = DetailMuted, fontSize = 11.sp)
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text(displayPrice?.let { String.format("%.2f", it) } ?: "数据未同步", fontSize = 22.sp, fontWeight = FontWeight.Bold)
                        Text(signalDayMove?.let { String.format("%+.2f%%", it) } ?: "当日涨跌未同步", color = if ((signalDayMove ?: 0.0) >= 0) DetailUp else DetailDown, fontSize = 11.sp)
                    }
                }
                if (pools.isNotEmpty()) {
                    Spacer(Modifier.height(8.dp))
                    Text("正式池：${pools.joinToString(" / ") { poolTitle(it) }}", color = DetailBlue, fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
                }
            }
        }

        if (tail != null) {
            item { DetailSectionTitle("尾盘决策上下文") }
            item {
                DetailCard {
                    DetailKey("尾盘捕获价", tail.price?.let { String.format("%.2f", it) } ?: "未同步")
                    DetailKey("尾盘评分", tail.tailScore?.let { String.format("%.1f", it) } ?: "未同步")
                    DetailKey("主力占比", tail.mainFlowPct?.let { String.format("%+.2f%%", it) } ?: "未同步")
                    DetailKey("风险", tail.risk)
                    DetailKey("Yunai行情核对", if (tail.yunaiVerified == true) "通过" else "未确认")
                    DetailKey("Yunai大单净流", tail.yunaiLargeNetInflow?.let { String.format("%+.2f", it) } ?: "未同步")
                    tail.reason?.let { Text(it, fontSize = 9.sp, color = DetailMuted) }
                }
            }
        }

        item { DetailSectionTitle("信号日事实") }
        item {
            DetailCard {
                DetailKey("信号/入池日期", date ?: "未关联正式批次")
                DetailKey("未复权入池收盘价", selection?.let { String.format("%.2f", it) } ?: "未同步")
                DetailKey("信号日涨跌", signalDayMove?.let { String.format("%+.2f%%", it) } ?: "未同步")
                DetailKey("成交额", (f?.amount ?: meta?.amount ?: tail?.amount)?.let(::money) ?: "未同步")
                DetailKey("换手率", (f?.turnover ?: meta?.turnover ?: tail?.turnover)?.let { String.format("%.2f%%", it) } ?: "未同步")
                DetailKey("主力净流入", (f?.mainNetFlow ?: meta?.mainNetFlow ?: tail?.mainNetFlow)?.let(::signedMoney) ?: "未同步")
                DetailKey("主力资金占比", (f?.mainFlowPct ?: meta?.mainFlowPct ?: tail?.mainFlowPct)?.let { String.format("%+.2f%%", it) } ?: "未同步")
                if (providers.isNotEmpty()) DetailKey("入池价核验", providers.joinToString(" + "))
                if (maxDiff != null) DetailKey("OHLC最大源差", String.format("%.4f%%", maxDiff * 100.0))
            }
        }

        item { DetailSectionTitle("因子与模型") }
        item {
            DetailCard {
                DetailKey("综合评分", (f?.score ?: meta?.score)?.let { String.format("%.1f / 100", it) } ?: "未同步")
                DetailKey("RS20", (f?.rs20 ?: meta?.rs)?.let { String.format("%+.2f%%", it) } ?: "未同步")
                DetailKey("RS60", (f?.rs60 ?: meta?.rs60)?.let { String.format("%+.2f%%", it) } ?: "未同步")
                DetailKey("多周期趋势", f?.mta ?: meta?.mta ?: tail?.mta ?: "未同步")
                DetailKey("置信度", f?.confidence ?: meta?.confidence ?: "未标注")
                DetailKey("B1两融", if ("B1" in pools) "已确认" else "未入池/数据不足")
                DetailKey("B2 ETF申赎", if ("B2" in pools) "已确认" else "未入池/数据不足")
                DetailKey("B3主力资金", if ("B3" in pools) "已确认" else "未入池")
                (f?.reason ?: meta?.reason)?.let { Text(it, fontSize = 9.sp, color = DetailMuted) }
            }
        }

        item { DetailSectionTitle("K线（历史详情截止所选日期）") }
        item {
            DetailCard {
                if (bars.size < 5) Text("K线数据暂不可用", color = DetailMuted)
                else {
                    CandleChart(bars.takeLast(40))
                    Spacer(Modifier.height(8.dp))
                    DetailKey("5日涨跌", kReturn(bars, 5)?.let { String.format("%+.2f%%", it) } ?: "未成熟")
                    DetailKey("20日涨跌", kReturn(bars, 20)?.let { String.format("%+.2f%%", it) } ?: "未成熟")
                    DetailKey("60日涨跌", kReturn(bars, 60)?.let { String.format("%+.2f%%", it) } ?: "未成熟")
                    DetailKey("距20日高点", distHigh(bars, 20)?.let { String.format("%+.2f%%", it) } ?: "未成熟")
                }
            }
        }

        item { DetailSectionTitle("策略 Forward Tracking") }
        item {
            DetailCard {
                if (perf == null || perf.length() == 0) {
                    Text(if (date == today) "该信号今天收盘形成；策略收益从下一交易日可成交开盘开始，因此今天不会把信号日前涨幅冒充策略收益。" else "Forward Tracking 尚未同步或入场价尚未通过验证。", fontSize = 10.sp, color = DetailMuted)
                } else {
                    DetailKey("入场规则", perf.optString("entryRule", "次一交易日开盘"))
                    DetailKey("实际入场日", perf.optString("entryDate", "—"))
                    DetailKey("验证入场价", if (perf.has("entryPrice")) String.format("%.2f", perf.optDouble("entryPrice")) else "—")
                    TrackingStrip(perf)
                    Spacer(Modifier.height(8.dp))
                    DetailKey("当前跟踪", detailValue(perf, "current"))
                    DetailKey("最大有利涨幅", detailValue(perf, "MFE"))
                    DetailKey("最大不利跌幅", detailValue(perf, "MAE"))
                    Text(if (snapshot?.performanceEligible == true) "该批次已通过审计，可纳入策略统计。" else "该批次为参考跟踪，不纳入胜率/Alpha或因子有效性统计。", fontSize = 9.sp, color = if (snapshot?.performanceEligible == true) DetailBlue else DetailMuted)
                }
            }
        }
    }
}'''
ds = replace_between(ds, '@Composable\nfun StockDetailScreen(', '@Composable\nprivate fun CandleChart(', stock_detail)
d.write_text(ds, encoding='utf-8')

# Version bump after v1.8 patch.
g = Path('app/build.gradle.kts')
gs = g.read_text(encoding='utf-8')
gs = gs.replace('versionCode = 19', 'versionCode = 20')
gs = gs.replace('versionName = "1.8.0"', 'versionName = "1.9.0"')
g.write_text(gs, encoding='utf-8')
