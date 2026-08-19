from pathlib import Path

# Final UI patch. It intentionally changes only USER-VISIBLE labels; JSON/status/pool keys
# stay in their original internal form to preserve compatibility.
p = Path('app/src/main/java/com/rui/astockstrategy/v6/V6Activity.kt')
s = p.read_text(encoding='utf-8')

# ---------- Snapshot stock facts ----------
old = '''data class StockMeta(\n    val code: String,\n    val name: String?,\n    val sector: String?,\n    val rs: Double?,\n    val mta: String?,\n    val score: Double?,\n    val reason: String?,\n    val selectionPrice: Double?,\n    val confidence: String?\n)'''
new = '''data class StockMeta(\n    val code: String,\n    val name: String?,\n    val sector: String?,\n    val rs: Double?,\n    val mta: String?,\n    val score: Double?,\n    val reason: String?,\n    val selectionPrice: Double?,\n    val confidence: String?,\n    val dayChangePct: Double?,\n    val dayOpen: Double?,\n    val dayClose: Double?,\n    val dayHigh: Double?,\n    val dayLow: Double?,\n    val dayRangePct: Double?,\n    val mainFlowPct: Double?\n)'''
if old in s:
    s = s.replace(old, new, 1)

old = '''                    num(x, "selectionPrice"),\n                    x.optString("confidence").takeIf { it.isNotBlank() }\n                )'''
new = '''                    num(x, "selectionPrice"),\n                    x.optString("confidence").takeIf { it.isNotBlank() },\n                    num(x, "changePct") ?: num(x, "dayChangePct"),\n                    num(x, "dayOpen"),\n                    num(x, "dayClose") ?: num(x, "selectionPrice"),\n                    num(x, "dayHigh"),\n                    num(x, "dayLow"),\n                    num(x, "dayRangePct"),\n                    num(x, "mainFlowPct")\n                )'''
if old in s:
    s = s.replace(old, new, 1)

# If mainlines[] is empty, show frozen selected-sector names rather than an apparently empty page.
old = 'mainlines = arrStrings(o.optJSONArray("mainlines")),'
new = '''mainlines = arrStrings(o.optJSONArray("mainlines")).ifEmpty {\n                val a = o.optJSONArray("selectedSectors")\n                if (a == null) emptyList() else (0 until a.length()).mapNotNull { i ->\n                    a.optJSONObject(i)?.optString("name")?.takeIf { it.isNotBlank() }\n                }.take(5)\n            },'''
s = s.replace(old, new)

# ---------- Stock pool row ----------
old = '''fun StockLiveRow(code: String, s: Snapshot, q: Quote?) {\n    val meta = s.stocks[code]'''
new = '''fun StockLiveRow(code: String, s: Snapshot, q: Quote?) {\n    val meta = s.stocks[code]\n    val currentPrice = q?.price ?: meta?.dayClose ?: meta?.selectionPrice\n    val dayChange = q?.change ?: meta?.dayChangePct\n    val dayHigh = q?.high ?: meta?.dayHigh\n    val dayLow = q?.low ?: meta?.dayLow\n    val rangePct = if (dayHigh != null && dayLow != null && dayLow > 0) (dayHigh / dayLow - 1.0) * 100.0 else meta?.dayRangePct'''
if old in s:
    s = s.replace(old, new, 1)

s = s.replace(
    'Text(q?.price?.let { String.format("%.2f", it) } ?: "—", fontWeight = FontWeight.Bold)',
    'Text(currentPrice?.let { String.format("%.2f", it) } ?: "—", fontWeight = FontWeight.Bold)'
)
s = s.replace(
    'Text(q?.change?.let(::pct) ?: "—", color = q?.change?.let(::pnl) ?: Muted, fontSize = 11.sp)',
    'Text(dayChange?.let(::pct) ?: "—", color = dayChange?.let(::pnl) ?: Muted, fontSize = 11.sp)'
)
s = s.replace(
    'val liveReturn = if (selection != null && selection > 0 && q?.price != null) (q.price / selection - 1.0) * 100.0 else null',
    'val liveReturn = if (selection != null && selection > 0 && currentPrice != null) (currentPrice / selection - 1.0) * 100.0 else null'
)

needle = '''            Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {\n                Text("入池价 ${selection?.let { String.format("%.2f", it) } ?: "—"}", fontSize = 10.sp, color = Muted)\n                Text("至今 ${liveReturn?.let { String.format("%+.2f%%", it) } ?: "—"}", fontSize = 10.sp, color = liveReturn?.let(::pnl) ?: Muted)\n            }'''
repl = '''            Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {\n                Text("冻结收盘价 ${selection?.let { String.format("%.2f", it) } ?: "—"}", fontSize = 10.sp, color = Muted)\n                Text("相对冻结价 ${liveReturn?.let { String.format("%+.2f%%", it) } ?: "—"}", fontSize = 10.sp, color = liveReturn?.let(::pnl) ?: Muted)\n            }\n            Spacer(Modifier.height(5.dp))\n            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {\n                Text("当日最高 ${dayHigh?.let { String.format("%.2f", it) } ?: "—"}", fontSize = 9.sp, color = Muted)\n                Text("当日最低 ${dayLow?.let { String.format("%.2f", it) } ?: "—"}", fontSize = 9.sp, color = Muted)\n                Text("理论高低区间 ${rangePct?.let { String.format("%.2f%%", it) } ?: "—"}", fontSize = 9.sp, color = Muted)\n            }\n            Spacer(Modifier.height(6.dp))\n            TradeAssistStrip(code, s, meta, q)'''
if needle in s:
    s = s.replace(needle, repl, 1)

# ---------- Conservative, auditable trading assistance ----------
marker = '''@Composable\nfun IndexCard(q: Quote?, modifier: Modifier) {'''
helpers = '''data class TradeAssist(val entry: String, val holding: String, val note: String)\n\nfun tradeAssist(code: String, s: Snapshot, meta: StockMeta?, q: Quote?): TradeAssist {\n    val price = q?.price ?: meta?.dayClose ?: meta?.selectionPrice\n    val high = q?.high ?: meta?.dayHigh\n    val low = q?.low ?: meta?.dayLow\n    val chg = q?.change ?: meta?.dayChangePct\n    val flow = meta?.mainFlowPct\n    if (price == null || high == null || low == null || low <= 0) {\n        return TradeAssist("条件不足，暂不介入", "条件不足，暂不判断离场", "缺少可靠价格区间时不生成交易提示")\n    }\n    val nearHigh = high > 0 && price / high >= 0.985\n    val nearLow = price / low <= 1.015\n    val pos = if (high > low) (price - low) / (high - low) else 0.5\n    val strongFlow = (flow ?: 0.0) >= 5.0\n    val entry = when {\n        (chg ?: 0.0) >= 8.0 && nearHigh -> "涨幅较大且接近日内高位，不宜追高"\n        (chg ?: 0.0) <= -4.0 || nearLow -> "价格处于弱势区，等待重新企稳"\n        strongFlow && pos in 0.30..0.72 && (chg ?: 0.0) in -1.5..5.0 -> "资金与价格结构尚可，可观察分批介入"\n        pos > 0.80 -> "位置偏高，等待回踩确认"\n        else -> "保持观察，等待价格与资金共振"\n    }\n    val holding = when {\n        (chg ?: 0.0) >= 7.0 && nearHigh -> "已有可卖持仓：接近日内高位，可考虑分批保护利润"\n        (chg ?: 0.0) <= -4.0 && nearLow -> "已有可卖持仓：弱势接近日内低位，关注保护性减仓"\n        strongFlow && pos >= 0.45 -> "已有可卖持仓：趋势未明显破坏，可继续观察"\n        else -> "已有可卖持仓：暂未触发明确保护条件"\n    }\n    val today = LocalDate.now(CnZone).toString()\n    val note = if (s.date == today)\n        "普通A股当日新买入不可当日卖出；离场提示仅适用于已有可卖持仓。"\n    else\n        "离场提示需结合你的实际成交价和持仓成本。"\n    return TradeAssist(entry, holding, note)\n}\n\n@Composable\nfun TradeAssistStrip(code: String, s: Snapshot, meta: StockMeta?, q: Quote?) {\n    val a = tradeAssist(code, s, meta, q)\n    Surface(color = Color(0xFFF0F3FA), shape = RoundedCornerShape(10.dp)) {\n        Column(Modifier.fillMaxWidth().padding(8.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {\n            Text("交易辅助", fontSize = 10.sp, fontWeight = FontWeight.Bold)\n            Text("介入参考：${a.entry}", fontSize = 9.sp, color = Ink)\n            Text("持仓保护：${a.holding}", fontSize = 9.sp, color = Ink)\n            Text(a.note, fontSize = 8.sp, color = Muted)\n        }\n    }\n}\n\nfun displayChoice(v: String): String = when (v) {\n    "B0" -> "基础强势"\n    "B1" -> "两融增强"\n    "B2" -> "指数基金申赎"\n    "B3" -> "主力资金"\n    "B12" -> "两融+指数基金"\n    "B13" -> "两融+主力资金"\n    "B23" -> "指数基金+主力资金"\n    "B4" -> "综合确认"\n    else -> v\n}\n\n'''
if marker in s and 'fun TradeAssistStrip(' not in s:
    s = s.replace(marker, helpers + marker, 1)

# Pool selector buttons show Chinese labels while internal values remain B0/B1/... .
s = s.replace('label = { Text(item, fontSize = 10.sp) }', 'label = { Text(displayChoice(item), fontSize = 10.sp) }')

# Tracking horizon display: keep JSON keys 1D/5D/... but show Chinese day labels.
old = '''        listOf("1D", "5D", "10D", "20D", "60D").forEach { h ->\n            Column('''
new = '''        listOf("1D" to "1日", "5D" to "5日", "10D" to "10日", "20D" to "20日", "60D" to "60日").forEach { (h, hLabel) ->\n            Column('''
if old in s:
    s = s.replace(old, new, 1)
s = s.replace('Text(h, fontSize = 8.sp, color = Muted)', 'Text(hLabel, fontSize = 8.sp, color = Muted)')

# ---------- User-facing Chinese terminology only (exact phrases, no internal-key rewrites) ----------
for a, b in {
    'Intraday Preview（盘中预览）': '盘中主线预览',
    'Latest Official / Snapshot': '最新正式冻结结果',
    'B4 Live Monitor（实时跟踪）': '综合确认池实时跟踪',
    'Data Status（数据状态）': '数据状态',
    'Time Machine（历史时间机器）': '历史回溯',
    'Mainline Preview': '主线预览',
    'Pool Quotes': '股票池行情',
    'Momentum': '动量强度',
    'Breadth': '上涨广度',
    'Flow': '资金流强度',
    'Score ${': '综合评分 ${',
    '已核对 / Verified': '已核对',
    'Cohort Forward Tracking': '批次后续收益跟踪',
}.items():
    s = s.replace(a, b)

# Preview mode and states are UI-only state values, so Chinese internal display-state names are safe.
s = s.replace('"盘中Preview"', '"盘中预览"')
s = s.replace('Choice(listOf("盘中预览", "Official"), mode)', 'Choice(listOf("盘中预览", "正式冻结"), mode)')
s = s.replace('"Confirmed Candidate"', '"确认候选"')
s = s.replace('"Candidate"', '"候选"')
s = s.replace('"Observe"', '"观察"')
s = s.replace('p.state == "确认候选"', 'p.state == "确认候选"')

# Exact visible labels.
s = s.replace('Key("Regime", s.regime)', 'Key("市场阶段", s.regime)')
s = s.replace('Key("Regime", snap.regime)', 'Key("市场阶段", snap.regime)')
s = s.replace('Key("主线", s.mainlines.joinToString(" / ").ifBlank { "—" })', 'Key("正式筛选板块", s.mainlines.joinToString(" / ").ifBlank { "无" })')
s = s.replace('Key("主线", snap.mainlines.joinToString(" / ").ifBlank { "—" })', 'Key("正式筛选板块", snap.mainlines.joinToString(" / ").ifBlank { "无" })')
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

# Status text emitted to screen; internal status comparisons remain untouched.
s = s.replace('return "行情 OFFLINE"', 'return "行情不可用"')
s = s.replace('return "行情 STALE ${age}s"', 'return "行情陈旧 ${age}秒"')
s = s.replace('return if (marketOpenNow()) "行情 LIVE ${age}s" else "行情 CLOSED ${quoteTime?.takeLast(6) ?: "已收盘"}"',
              'return if (marketOpenNow()) "行情实时 ${age}秒" else "行情已收盘 ${quoteTime?.takeLast(6) ?: "已收盘"}"')

p.write_text(s, encoding='utf-8')

# ---------- Stock detail ----------
d = Path('app/src/main/java/com/rui/astockstrategy/v6/DetailScreens.kt')
ds = d.read_text(encoding='utf-8')

old = '''    val mainNetFlow: Double?,\n    val mainFlowPct: Double?,\n    val pools: List<String>\n)'''
new = '''    val mainNetFlow: Double?,\n    val mainFlowPct: Double?,\n    val dayOpen: Double?,\n    val dayClose: Double?,\n    val dayHigh: Double?,\n    val dayLow: Double?,\n    val dayRangePct: Double?,\n    val pools: List<String>\n)'''
if old in ds:
    ds = ds.replace(old, new, 1)

old = '''            mainNetFlow = jsonNum(x, "mainNetFlow"),\n            mainFlowPct = jsonNum(x, "mainFlowPct"),\n            pools = ps.distinct().sorted()'''
new = '''            mainNetFlow = jsonNum(x, "mainNetFlow"),\n            mainFlowPct = jsonNum(x, "mainFlowPct"),\n            dayOpen = jsonNum(x, "dayOpen"),\n            dayClose = jsonNum(x, "dayClose") ?: jsonNum(x, "selectionPrice"),\n            dayHigh = jsonNum(x, "dayHigh"),\n            dayLow = jsonNum(x, "dayLow"),\n            dayRangePct = jsonNum(x, "dayRangePct"),\n            pools = ps.distinct().sorted()'''
if old in ds:
    ds = ds.replace(old, new, 1)

needle = '''        item { DetailSectionTitle("因子") }'''
insert = '''        item { DetailSectionTitle("当日交易事实") }\n        item {\n            DetailCard {\n                val hi = quote?.high ?: f?.dayHigh\n                val lo = quote?.low ?: f?.dayLow\n                val op = f?.dayOpen\n                val cl = quote?.price ?: f?.dayClose\n                val range = if (hi != null && lo != null && lo > 0) (hi / lo - 1.0) * 100.0 else f?.dayRangePct\n                DetailKey("当日开盘", op?.let { String.format("%.2f", it) } ?: "—")\n                DetailKey("当日最高", hi?.let { String.format("%.2f", it) } ?: "—")\n                DetailKey("当日最低", lo?.let { String.format("%.2f", it) } ?: "—")\n                DetailKey("当前/收盘", cl?.let { String.format("%.2f", it) } ?: "—")\n                DetailKey("理论高低区间", range?.let { String.format("%.2f%%", it) } ?: "—")\n                Text("理论高低区间只描述当天最高与最低的价格跨度，不代表按时间顺序可实现的交易利润。", color = DetailMuted, fontSize = 9.sp)\n            }\n        }\n        item { DetailSectionTitle("交易辅助") }\n        item {\n            if (snapshot != null) {\n                val a = tradeAssist(code, snapshot, meta, quote)\n                DetailCard {\n                    DetailKey("介入参考", a.entry)\n                    DetailKey("持仓保护", a.holding)\n                    Text(a.note, color = DetailMuted, fontSize = 9.sp)\n                    Text("尚未录入你的实际成交价与持仓数量，因此离场提示目前只依据行情结构。后续加入“我的持仓”后，再按真实成本计算止盈、止损和仓位。", color = DetailMuted, fontSize = 9.sp)\n                }\n            } else {\n                DetailNotice("没有对应冻结批次，暂不生成交易辅助提示。")\n            }\n        }\n\n        item { DetailSectionTitle("因子") }'''
if needle in ds and 'DetailSectionTitle("当日交易事实")' not in ds:
    ds = ds.replace(needle, insert, 1)

# Exact visible phrase translations only.
ds = ds.replace('"该股票不是当前所选 Daily Cohort 的冻结入选股；仍可查看行情和趋势。"', '"该股票不是当前所选每日冻结批次的入选股；仍可查看行情和趋势。"')
ds = ds.replace('DetailKey("两融增强 B1"', 'DetailKey("两融增强池"')
ds = ds.replace('DetailKey("ETF增强 B2"', 'DetailKey("指数基金一级申赎资金池"')
ds = ds.replace('DetailKey("ETF资金 B2"', 'DetailKey("指数基金一级申赎资金池"')
ds = ds.replace('DetailKey("主力资金 B3"', 'DetailKey("主力资金确认池"')
ds = ds.replace('DetailKey("两融+ETF B12"', 'DetailKey("两融与指数基金双确认池"')
ds = ds.replace('DetailKey("两融+主力 B13"', 'DetailKey("两融与主力资金双确认池"')
ds = ds.replace('DetailKey("ETF+主力 B23"', 'DetailKey("指数基金与主力资金双确认池"')
ds = ds.replace('DetailKey("三资金/综合 B4"', 'DetailKey("综合确认池"')
ds = ds.replace('Text("B1/B2没有正式数据时保持空值，不用其他口径代替。"', 'Text("两融和指数基金一级申赎数据没有正式来源时保持空值，不用其他口径代替。"')
ds = ds.replace('DetailKey("ETF申赎关联", "—")', 'DetailKey("指数基金一级申赎关联", "—")')
ds = ds.replace('DetailSectionTitle("K线")', 'DetailSectionTitle("价格走势")')
ds = ds.replace('Text("K线数据暂不可用"', 'Text("价格走势数据暂不可用"')
ds = ds.replace('"正在读取个股行情、K线和策略因子…"', '"正在读取个股行情、价格走势和策略因子…"')
ds = ds.replace('DetailKey("最大有利涨幅", detailValue(perf, "MFE"))', 'DetailKey("最大浮盈", detailValue(perf, "MFE"))')
ds = ds.replace('DetailKey("最大不利跌幅", detailValue(perf, "MAE"))', 'DetailKey("最大回撤", detailValue(perf, "MAE"))')

d.write_text(ds, encoding='utf-8')

# ---------- Tail screen ----------
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
ts = ts.replace('"[$label]" else label', '"[$label]" else label')
ts = ts.replace('"$intraday  [15:00 Final]"', '"$intraday  [15:00 最终]"')
ts = ts.replace('"$intraday  15:00 Final"', '"$intraday  15:00 最终"')
ts = ts.replace('Text("${s.pools.joinToString(" · ")} · ${s.mta ?: "趋势待同步"} · ${s.risk}"',
                'Text("${s.pools.joinToString(" · ") { tailPoolLabel(it) }} · ${s.mta ?: "趋势待同步"} · ${s.risk}"')
marker = 'private fun tailTime(v: String): String = if (v.length >= 19) v.substring(11, 19) else v'
helper = '''private fun tailPoolLabel(v: String): String = when (v) {\n    "TB0" -> "基础强度"\n    "TB3" -> "主力资金确认"\n    "TailCore" -> "尾盘核心"\n    else -> v\n}\n\n'''
if marker in ts and 'tailPoolLabel(' not in ts:
    ts = ts.replace(marker, helper + marker, 1)
t.write_text(ts, encoding='utf-8')

# v1.9.0 after v1.8 rolling-tail patch.
g = Path('app/build.gradle.kts')
gs = g.read_text(encoding='utf-8')
gs = gs.replace('versionCode = 19', 'versionCode = 20')
gs = gs.replace('versionName = "1.8.0"', 'versionName = "1.9.0"')
g.write_text(gs, encoding='utf-8')
