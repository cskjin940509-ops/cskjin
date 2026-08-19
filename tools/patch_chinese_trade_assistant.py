from pathlib import Path


def replace_between(text: str, start: str, end: str, replacement: str) -> str:
    a = text.find(start)
    if a < 0:
        raise SystemExit(f'start marker not found: {start}')
    b = text.find(end, a + len(start))
    if b < 0:
        raise SystemExit(f'end marker not found: {end}')
    return text[:a] + replacement.rstrip() + "\n\n" + text[b:]


# This patch runs LAST, after the v2.0 drill-down patch. It changes user-visible
# terminology only, while preserving JSON/status/pool keys for compatibility.
p = Path('app/src/main/java/com/rui/astockstrategy/v6/V6Activity.kt')
s = p.read_text(encoding='utf-8')

# -----------------------------------------------------------------------------
# 1) Extend the already-rich v2.0 stock model with verified same-day OHLC facts.
# -----------------------------------------------------------------------------
old = '''    val dayChangePct: Double?,\n    val amount: Double?,\n    val turnover: Double?,'''
new = '''    val dayChangePct: Double?,\n    val dayOpen: Double?,\n    val dayClose: Double?,\n    val dayHigh: Double?,\n    val dayLow: Double?,\n    val dayRangePct: Double?,\n    val amount: Double?,\n    val turnover: Double?,'''
if old in s and 'val dayHigh: Double?' not in s:
    s = s.replace(old, new, 1)

old = '''                    dayChangePct = num(x, "changePct"),\n                    amount = num(x, "amount"),'''
new = '''                    dayChangePct = num(x, "changePct") ?: num(x, "dayChangePct"),\n                    dayOpen = num(x, "dayOpen"),\n                    dayClose = num(x, "dayClose") ?: num(x, "selectionPrice"),\n                    dayHigh = num(x, "dayHigh"),\n                    dayLow = num(x, "dayLow"),\n                    dayRangePct = num(x, "dayRangePct"),\n                    amount = num(x, "amount"),'''
if old in s:
    s = s.replace(old, new, 1)

# -----------------------------------------------------------------------------
# 2) Replace pool stock row with frozen OHLC fallback + trading-assistance signal.
# -----------------------------------------------------------------------------
stock_row = r'''@Composable
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
                    Text("$code · ${meta?.sector ?: "未分类"} · 点开详情", fontSize = 10.sp, color = Muted)
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
                Text("主力 ${meta?.mainNetFlow?.let(::signedMoney) ?: "未同步"}", fontSize = 9.sp, color = Muted)
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
}'''
s = replace_between(s, '@Composable\nfun StockLiveRow(', '@Composable\nfun HistoryStockRow(', stock_row)

# -----------------------------------------------------------------------------
# 3) Conservative trading assistance. This is a transparent rules layer, not
# an execution engine. It never invents a signal when core quote fields are absent.
# -----------------------------------------------------------------------------
choice_marker = '@Composable\nfun Choice(items: List<String>, value: String, onChange: (String) -> Unit) {'
if 'data class TradeAssist(' not in s:
    helpers = r'''data class TradeAssist(val entry: String, val holding: String, val note: String)

fun tradeAssist(code: String, s: Snapshot, meta: StockMeta?, q: Quote?): TradeAssist {
    val price = q?.price ?: meta?.dayClose ?: meta?.selectionPrice
    val high = q?.high ?: meta?.dayHigh
    val low = q?.low ?: meta?.dayLow
    val chg = q?.change ?: meta?.dayChangePct
    val flow = meta?.mainFlowPct
    if (price == null || high == null || low == null || low <= 0) {
        return TradeAssist("条件不足，暂不介入", "条件不足，暂不判断离场", "缺少可靠价格区间时不生成交易提示。")
    }
    val nearHigh = high > 0 && price / high >= 0.985
    val nearLow = price / low <= 1.015
    val rangePosition = if (high > low) (price - low) / (high - low) else 0.5
    val strongFlow = (flow ?: 0.0) >= 5.0

    val entry = when {
        (chg ?: 0.0) >= 8.0 && nearHigh -> "涨幅较大且接近日内高位，不宜追高"
        (chg ?: 0.0) <= -4.0 || nearLow -> "价格处于弱势区，等待重新企稳"
        strongFlow && rangePosition in 0.30..0.72 && (chg ?: 0.0) in -1.5..5.0 -> "资金与价格结构尚可，可观察分批介入"
        rangePosition > 0.80 -> "价格位置偏高，等待回踩确认"
        else -> "保持观察，等待价格与资金共振"
    }
    val holding = when {
        (chg ?: 0.0) >= 7.0 && nearHigh -> "已有可卖持仓：接近日内高位，可考虑分批保护利润"
        (chg ?: 0.0) <= -4.0 && nearLow -> "已有可卖持仓：弱势接近日内低位，关注保护性减仓"
        strongFlow && rangePosition >= 0.45 -> "已有可卖持仓：趋势未明显破坏，可继续观察"
        else -> "已有可卖持仓：暂未触发明确保护条件"
    }
    val today = LocalDate.now(CnZone).toString()
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
    "B4" -> "综合确认"
    else -> v
}

'''
    if choice_marker not in s:
        raise SystemExit('Choice marker missing')
    s = s.replace(choice_marker, helpers + choice_marker, 1)

# Pool selector keeps B-code internal values, but button text is Chinese.
s = s.replace('label = { Text(item, fontSize = 10.sp) }', 'label = { Text(displayChoice(item), fontSize = 10.sp) }')

# -----------------------------------------------------------------------------
# 4) Chinese professional terminology in the main app. Exact visible phrases only.
# -----------------------------------------------------------------------------
visible_replacements = {
    '历史时间机器': '历史回溯',
    'Forward Tracking': '后续收益跟踪',
    'Score ${': '综合评分 ${',
    '已核对 / Verified': '已核对',
    '部分核对 / 可跟踪': '部分核对 / 可参考跟踪',
    'Alpha': '超额收益',
    'point-in-time': '时点冻结',
    'Data Status（数据状态）': '数据状态',
    'Intraday Preview（盘中预览）': '盘中主线预览',
    'Latest Official / Snapshot': '最新正式冻结结果',
    'B4 Live Monitor（实时跟踪）': '综合确认池实时跟踪',
    'Mainline Preview': '主线预览',
    'Pool Quotes': '股票池行情',
    'Momentum': '动量强度',
    'Breadth': '上涨广度',
    'Flow': '资金流强度',
}
for a, b in visible_replacements.items():
    s = s.replace(a, b)

# Main-screen exact B-code phrases.
s = s.replace('Key("B0 / B3 / B4", "${s.pools["B0"].orEmpty().size} / ${s.pools["B3"].orEmpty().size} / ${s.pools["B4"].orEmpty().size} 只")',
              'Key("基础强势 / 主力资金 / 综合确认", "${s.pools["B0"].orEmpty().size} / ${s.pools["B3"].orEmpty().size} / ${s.pools["B4"].orEmpty().size} 只")')
s = s.replace('Title(if (b4.isNotEmpty()) "B4 综合确认池" else "正式股票候选")', 'Title(if (b4.isNotEmpty()) "综合确认池" else "正式股票候选")')

# poolTitle values: internal keys unchanged.
s = s.replace('"B0" -> "B0 基础池"', '"B0" -> "基础强势池"')
s = s.replace('"B1" -> "B1 两融增强"', '"B1" -> "两融增强池"')
s = s.replace('"B2" -> "B2 ETF资金"', '"B2" -> "指数基金一级申赎资金池"')
s = s.replace('"B3" -> "B3 主力资金"', '"B3" -> "主力资金确认池"')
s = s.replace('"B12" -> "B12 两融+ETF"', '"B12" -> "两融与指数基金双确认池"')
s = s.replace('"B13" -> "B13 两融+主力"', '"B13" -> "两融与主力资金双确认池"')
s = s.replace('"B23" -> "B23 ETF+主力"', '"B23" -> "指数基金与主力资金双确认池"')
s = s.replace('"B4" -> "B4 三资金/综合确认"', '"B4" -> "综合确认池"')
s = s.replace('Text("单因子 / 基础"', 'Text("基础与单因子确认"')
s = s.replace('Text("组合确认"', 'Text("多因子联合确认"')

# Official/preview mode labels: internal Snapshot.status remains "Official".
s = s.replace('var mode by remember { mutableStateOf("盘中Preview") }', 'var mode by remember { mutableStateOf("盘中预览") }')
s = s.replace('Choice(listOf("盘中Preview", "Official"), mode)', 'Choice(listOf("盘中预览", "正式冻结"), mode)')
s = s.replace('if (mode == "盘中Preview")', 'if (mode == "盘中预览")')

# Preview state values are local UI-only states.
s = s.replace('"Confirmed Candidate"', '"确认候选"')
s = s.replace('"Candidate"', '"候选"')
s = s.replace('"Observe"', '"观察"')

# Tracking horizon display: keep data keys, show Chinese labels.
old = '''        listOf("1D", "5D", "10D", "20D", "60D").forEach { h ->\n            Column('''
new = '''        listOf("1D" to "1日", "5D" to "5日", "10D" to "10日", "20D" to "20日", "60D" to "60日").forEach { (h, hLabel) ->\n            Column('''
if old in s:
    s = s.replace(old, new, 1)
s = s.replace('Text(h, fontSize = 8.sp, color = Muted)', 'Text(hLabel, fontSize = 8.sp, color = Muted)')

# Data status text.
s = s.replace('return "行情 OFFLINE"', 'return "行情不可用"')
s = s.replace('return "行情 STALE ${age}s"', 'return "行情陈旧 ${age}秒"')
s = s.replace('return if (marketOpenNow()) "行情 LIVE ${age}s" else "行情 CLOSED ${quoteTime?.takeLast(6) ?: "已收盘"}"',
              'return if (marketOpenNow()) "行情实时 ${age}秒" else "行情已收盘 ${quoteTime?.takeLast(6) ?: "已收盘"}"')

p.write_text(s, encoding='utf-8')

# -----------------------------------------------------------------------------
# 5) Stock/sector detail: same-day OHLC + trading assistance + Chinese terminology.
# -----------------------------------------------------------------------------
d = Path('app/src/main/java/com/rui/astockstrategy/v6/DetailScreens.kt')
ds = d.read_text(encoding='utf-8')

# Extend final v2 StockFacts shape.
old = '''    val mainFlowPct: Double?,\n    val pools: List<String>,\n    val priceProviders: List<String>,'''
new = '''    val mainFlowPct: Double?,\n    val dayOpen: Double?,\n    val dayClose: Double?,\n    val dayHigh: Double?,\n    val dayLow: Double?,\n    val dayRangePct: Double?,\n    val pools: List<String>,\n    val priceProviders: List<String>,'''
if old in ds and 'val dayHigh: Double?' not in ds:
    ds = ds.replace(old, new, 1)

old = '''            mainFlowPct = jsonNum(x, "mainFlowPct"),\n            pools = ps.distinct().sorted(),'''
new = '''            mainFlowPct = jsonNum(x, "mainFlowPct"),\n            dayOpen = jsonNum(x, "dayOpen"),\n            dayClose = jsonNum(x, "dayClose") ?: jsonNum(x, "selectionPrice"),\n            dayHigh = jsonNum(x, "dayHigh"),\n            dayLow = jsonNum(x, "dayLow"),\n            dayRangePct = jsonNum(x, "dayRangePct"),\n            pools = ps.distinct().sorted(),'''
if old in ds:
    ds = ds.replace(old, new, 1)

# Add objective same-day facts + the same trading-assistance rule to StockDetailScreen.
needle = '        item { DetailSectionTitle("因子与模型") }'
insert = r'''        item { DetailSectionTitle("当日交易事实") }
        item {
            DetailCard {
                val hi = if (historical) f?.dayHigh ?: meta?.dayHigh else quote?.high ?: f?.dayHigh ?: meta?.dayHigh
                val lo = if (historical) f?.dayLow ?: meta?.dayLow else quote?.low ?: f?.dayLow ?: meta?.dayLow
                val op = f?.dayOpen ?: meta?.dayOpen
                val cl = if (historical) f?.dayClose ?: meta?.dayClose ?: selection else quote?.price ?: f?.dayClose ?: meta?.dayClose ?: selection
                val range = if (hi != null && lo != null && lo > 0) (hi / lo - 1.0) * 100.0 else f?.dayRangePct ?: meta?.dayRangePct
                DetailKey("当日开盘", op?.let { String.format("%.2f", it) } ?: "未同步")
                DetailKey("当日最高", hi?.let { String.format("%.2f", it) } ?: "未同步")
                DetailKey("当日最低", lo?.let { String.format("%.2f", it) } ?: "未同步")
                DetailKey("当前/收盘", cl?.let { String.format("%.2f", it) } ?: "未同步")
                DetailKey("理论高低区间", range?.let { String.format("%.2f%%", it) } ?: "未同步")
                Text("理论高低区间只描述最高与最低的价格跨度，不代表按时间顺序可实现的交易利润。", color = DetailMuted, fontSize = 9.sp)
            }
        }
        item { DetailSectionTitle("交易辅助") }
        item {
            if (snapshot != null) {
                val a = tradeAssist(code, snapshot, meta, if (historical) null else quote)
                DetailCard {
                    DetailKey("介入参考", a.entry)
                    DetailKey("持仓保护", a.holding)
                    Text(a.note, color = DetailMuted, fontSize = 9.sp)
                    Text("尚未录入你的实际成交价与持仓数量，因此离场提示目前只依据行情结构；加入“我的持仓”后再按真实成本计算止盈、止损和仓位。", color = DetailMuted, fontSize = 9.sp)
                }
            } else {
                DetailNotice("没有对应冻结批次，暂不生成交易辅助提示。")
            }
        }

        item { DetailSectionTitle("因子与模型") }'''
if needle in ds and 'DetailSectionTitle("当日交易事实")' not in ds:
    ds = ds.replace(needle, insert, 1)

# The v1.9 detail template exposes a lightweight snapshot-stock record without
# the money-flow properties. In detail rows, the complete StockFacts object `f`
# is the authoritative frozen source for those two fields. Keep the richer
# StockMeta use in V6Activity unchanged.
ds = ds.replace('meta?.mainNetFlow', 'f?.mainNetFlow')
ds = ds.replace('meta?.mainFlowPct', 'f?.mainFlowPct')

# Exact visible finance terms; internal JSON keys remain unchanged.
ds = ds.replace('DetailKey("RS20",', 'DetailKey("20日相对强弱",')
ds = ds.replace('DetailKey("RS60",', 'DetailKey("60日相对强弱",')
ds = ds.replace('DetailKey("B1两融",', 'DetailKey("两融增强",')
ds = ds.replace('DetailKey("B2 ETF申赎",', 'DetailKey("指数基金一级申赎",')
ds = ds.replace('DetailKey("B3主力资金",', 'DetailKey("主力资金确认",')
ds = ds.replace('DetailKey("Yunai行情核对",', 'DetailKey("云AI量化行情核对",')
ds = ds.replace('DetailKey("Yunai大单净流",', 'DetailKey("云AI量化大单净流入",')
ds = ds.replace('DetailKey("OHLC最大源差",', 'DetailKey("开高低收最大源差",')
ds = ds.replace('DetailSectionTitle("K线（历史详情截止所选日期）")', 'DetailSectionTitle("价格走势（历史详情截止所选日期）")')
ds = ds.replace('"正在读取行情、策略因子、K线和跟踪数据…"', '"正在读取行情、策略因子、价格走势和收益跟踪数据…"')
ds = ds.replace('"当前 Tracking"', '"当前跟踪收益"')
ds = ds.replace('"MFE"', '"MFE"')  # data key, deliberately unchanged
# Labels around MFE/MAE introduced by v2 sector tracking.
ds = ds.replace('DetailKey("MFE", detailValue(sectorPerf, "MFE"))', 'DetailKey("最大浮盈", detailValue(sectorPerf, "MFE"))')
ds = ds.replace('DetailKey("MAE", detailValue(sectorPerf, "MAE"))', 'DetailKey("最大回撤", detailValue(sectorPerf, "MAE"))')
ds = ds.replace('"参考 Tracking · 该批次不进入胜率、Alpha或因子成绩统计。"', '"参考收益跟踪 · 该批次不进入胜率、超额收益或因子成绩统计。"')
ds = ds.replace('"从正式信号后的下一交易日可成交开盘起算，不把信号日涨幅计入策略收益。"', '"从正式信号后的下一交易日可成交开盘起算，不把信号日涨幅计入策略收益。"')
# Old detail phrases if still present after prior patches.
ds = ds.replace('DetailSectionTitle("K线")', 'DetailSectionTitle("价格走势")')
ds = ds.replace('Text("K线数据暂不可用"', 'Text("价格走势数据暂不可用"')
ds = ds.replace('DetailKey("ETF申赎关联",', 'DetailKey("指数基金一级申赎关联",')
ds = ds.replace('DetailKey("最大有利涨幅", detailValue(perf, "MFE"))', 'DetailKey("最大浮盈", detailValue(perf, "MFE"))')
ds = ds.replace('DetailKey("最大不利跌幅", detailValue(perf, "MAE"))', 'DetailKey("最大回撤", detailValue(perf, "MAE"))')

d.write_text(ds, encoding='utf-8')

# -----------------------------------------------------------------------------
# 6) Tail screen: no English pool abbreviations or English status words visible.
# -----------------------------------------------------------------------------
t = Path('app/src/main/java/com/rui/astockstrategy/v6/TailDecision.kt')
ts = t.read_text(encoding='utf-8')
ts = ts.replace('Text(if (current.isFinal) "尾盘最终核心池 TailCore" else "尾盘实时核心池 TailCore"',
                'Text(if (current.isFinal) "尾盘最终核心池" else "尾盘实时核心池"')
ts = ts.replace('Text("TB0基础强度 ∩ TB3主力资金确认；每轮按当时数据重新排序。"',
                'Text("基础强度与主力资金同时确认；每轮按当时数据重新排序。"')
ts = ts.replace('MiniMetric("RS20"', 'MiniMetric("20日相对强弱"')
ts = ts.replace('"这是15:00后第一次成功计算并锁定的 TailFinal（尾盘最终池），后续不会用盘后数据或未来表现改写。收盘 Official（正式池）仍会独立计算。"',
                '"这是15:00后第一次成功计算并锁定的尾盘最终池，后续不会用盘后数据或未来表现改写。收盘正式股票池仍会独立计算。"')
ts = ts.replace('"当前是 TailLive（尾盘滚动池），不是最终结果。14:30后每5分钟重新计算一次，15:00后第一次成功结果会切换为 TailFinal 并锁定。"',
                '"当前是尾盘滚动池，不是最终结果。14:30后每5分钟重新计算一次，15:00后第一次成功结果会切换为尾盘最终池并锁定。"')
ts = ts.replace('"$intraday  [15:00 Final]"', '"$intraday  [15:00 最终]"')
ts = ts.replace('"$intraday  15:00 Final"', '"$intraday  15:00 最终"')
ts = ts.replace('Text("${s.pools.joinToString(" · ")} · ${s.mta ?: "趋势待同步"} · ${s.risk}"',
                'Text("${s.pools.joinToString(" · ") { tailPoolLabel(it) }} · ${s.mta ?: "趋势待同步"} · ${s.risk}"')
ts = ts.replace('Text("Yunai ${if (s.yunaiVerified == true) "行情已核对" else "核对未确认"} · 大单 ${s.yunaiLargeNetInflow?.let { String.format("%+.0f", it) } ?: "未同步"}"',
                'Text("云AI量化 ${if (s.yunaiVerified == true) "行情已核对" else "核对未确认"} · 大单净流入 ${s.yunaiLargeNetInflow?.let { String.format("%+.0f", it) } ?: "未同步"}"')
marker = 'private fun tailTime(v: String): String = if (v.length >= 19) v.substring(11, 19) else v'
if marker in ts and 'private fun tailPoolLabel(' not in ts:
    helper = '''private fun tailPoolLabel(v: String): String = when (v) {\n    "TB0" -> "基础强度"\n    "TB3" -> "主力资金确认"\n    "TailCore" -> "尾盘核心"\n    else -> v\n}\n\n'''
    ts = ts.replace(marker, helper + marker, 1)
t.write_text(ts, encoding='utf-8')

# v2.1 follows v2.0 full drill-down.
g = Path('app/build.gradle.kts')
gs = g.read_text(encoding='utf-8')
gs = gs.replace('versionCode = 21', 'versionCode = 22')
gs = gs.replace('versionName = "2.0.0"', 'versionName = "2.1.0"')
g.write_text(gs, encoding='utf-8')
