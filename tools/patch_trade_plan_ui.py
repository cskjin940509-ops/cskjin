from pathlib import Path
import re

p=Path('app/src/main/java/com/rui/astockstrategy/v6/V6Activity.kt')
s=p.read_text(encoding='utf-8')

# Quote: current-session open is needed for live forward tracking from next-day open.
s=s.replace('''    val price: Double?,\n    val prev: Double?,\n    val change: Double?,''','''    val price: Double?,\n    val prev: Double?,\n    val open: Double?,\n    val change: Double?,''')
s=s.replace('''                    prev = f.getOrNull(4)?.toDoubleOrNull(),\n                    change = f.getOrNull(32)?.toDoubleOrNull(),''','''                    prev = f.getOrNull(4)?.toDoubleOrNull(),\n                    open = f.getOrNull(5)?.toDoubleOrNull(),\n                    change = f.getOrNull(32)?.toDoubleOrNull(),''')

# Frozen signal-day return belongs in StockMeta even when live quote transport is stale.
s=s.replace('''    val selectionPrice: Double?,\n    val confidence: String?\n)''','''    val selectionPrice: Double?,\n    val confidence: String?,\n    val signalDayChangePct: Double? = null\n)''')
s=s.replace('''                    num(x, "selectionPrice"),\n                    x.optString("confidence").takeIf { it.isNotBlank() }\n                )''','''                    num(x, "selectionPrice"),\n                    x.optString("confidence").takeIf { it.isNotBlank() },\n                    num(x, "changePct")\n                )''')

# Keep selected formal sectors visible when no sector crosses the stricter confirmed-mainline threshold.
if 'val selectedSectorNames: List<String>' not in s:
    s=s.replace('''    val mainlines: List<String>,\n    val pools: Map<String, List<String>>,''','''    val mainlines: List<String>,\n    val selectedSectorNames: List<String>,\n    val pools: Map<String, List<String>>,''')

needle='''        return Snapshot(\n            date = date,'''
if needle in s and 'val selectedSectorNames = run {' not in s:
    ins='''        val selectedSectorNames = run {\n            val a = o.optJSONArray("selectedSectors")\n            if (a == null) emptyList() else (0 until a.length()).mapNotNull { i -> a.optJSONObject(i)?.optString("name")?.takeIf { it.isNotBlank() } }\n        }\n        return Snapshot(\n            date = date,'''
    s=s.replace(needle,ins,1)
s=s.replace('''            mainlines = arrStrings(o.optJSONArray("mainlines")),\n            pools = pools,''','''            mainlines = arrStrings(o.optJSONArray("mainlines")),\n            selectedSectorNames = selectedSectorNames,\n            pools = pools,''')

# Official display fallback.
s=s.replace('Key("主线", s.mainlines.joinToString(" / ").ifBlank { "—" })','Key("正式板块", officialSectorNames(s).joinToString(" / ").ifBlank { "—" })')
s=s.replace('Key("主线", snap.mainlines.joinToString(" / ").ifBlank { "—" })','Key("正式板块", officialSectorNames(snap).joinToString(" / ").ifBlank { "—" })')

old='''                if (s.mainlines.isEmpty()) item { EmptyCard("该日无主线") }\n                items(s.mainlines) { name ->'''
new='''                val formalNames = officialSectorNames(s)\n                if (s.mainlines.isEmpty() && formalNames.isNotEmpty()) item { Notice("本日没有板块达到‘确认主线’阈值；下面仍展示收盘正式Top板块，不把它们冒充确认主线。") }\n                if (formalNames.isEmpty()) item { EmptyCard("该日无正式板块结果") }\n                items(formalNames) { name ->'''
s=s.replace(old,new)

# Equal-sized two-row pool selector: no label-dependent segmented widths.
pattern=r'@Composable\nfun PoolSelector\(value: String, onChange: \(String\) -> Unit\) \{.*?(?=@Composable\nfun Choice)'
replacement='''@Composable\nfun PoolSelector(value: String, onChange: (String) -> Unit) {\n    Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {\n        Text("基础与单因子确认", fontSize = 10.sp, color = Muted, fontWeight = FontWeight.SemiBold)\n        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {\n            listOf("B0" to "基础", "B1" to "两融", "B2" to "ETF", "B3" to "主力").forEach { (p, label) ->\n                PoolBox(p, label, value == p, Modifier.weight(1f)) { onChange(p) }\n            }\n        }\n        Text("多联合确认", fontSize = 10.sp, color = Muted, fontWeight = FontWeight.SemiBold)\n        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {\n            listOf("B12" to "融+ETF", "B13" to "融+主力", "B23" to "ETF+主", "B4" to "综合").forEach { (p, label) ->\n                PoolBox(p, label, value == p, Modifier.weight(1f)) { onChange(p) }\n            }\n        }\n        Text("当前：${poolTitle(value)}", fontSize = 10.sp, color = Blue)\n    }\n}\n\n@Composable\nfun PoolBox(pool: String, label: String, selected: Boolean, modifier: Modifier, onClick: () -> Unit) {\n    Surface(\n        modifier = modifier.height(48.dp).clickable(onClick = onClick),\n        color = if (selected) SoftBlue else Color.White,\n        shape = RoundedCornerShape(11.dp),\n        tonalElevation = if (selected) 1.dp else 0.dp\n    ) {\n        Column(Modifier.fillMaxSize(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {\n            Text(pool, fontSize = 10.sp, fontWeight = FontWeight.Bold, color = if (selected) Blue else Ink)\n            Text(label, fontSize = 8.sp, color = Muted, maxLines = 1)\n        }\n    }\n}\n\n'''
s=re.sub(pattern,replacement,s,flags=re.S)

# Rich current/signal-day return card.
pattern=r'@Composable\nfun StockLiveRow\(code: String, s: Snapshot, q: Quote\?\) \{.*?(?=@Composable\nfun HistoryStockRow)'
replacement='''@Composable\nfun StockLiveRow(code: String, s: Snapshot, q: Quote?) {\n    val meta = s.stocks[code]\n    Card(shape = RoundedCornerShape(15.dp)) {\n        Column(Modifier.padding(12.dp)) {\n            Row {\n                Column(Modifier.weight(1f)) {\n                    Text(meta?.name ?: q?.name ?: code, fontWeight = FontWeight.Bold)\n                    Text("$code · ${meta?.sector ?: "—"}", fontSize = 10.sp, color = Muted)\n                }\n                Column(horizontalAlignment = Alignment.End) {\n                    Text(q?.price?.let { String.format("%.2f", it) } ?: meta?.selectionPrice?.let { String.format("%.2f", it) } ?: "—", fontWeight = FontWeight.Bold)\n                    val shownChange = q?.change ?: meta?.signalDayChangePct\n                    Text(shownChange?.let(::pct) ?: "—", color = shownChange?.let(::pnl) ?: Muted, fontSize = 11.sp)\n                }\n            }\n            val selection = meta?.selectionPrice\n            val liveFromSignalClose = if (selection != null && selection > 0 && q?.price != null) (q.price / selection - 1.0) * 100.0 else null\n            val today = LocalDate.now(CnZone).toString()\n            val openTrack = if (s.date < today && q?.open != null && q.open > 0 && q.price != null) (q.price / q.open - 1.0) * 100.0 else null\n            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {\n                Text("信号日 ${meta?.signalDayChangePct?.let { String.format("%+.2f%%", it) } ?: "—"}", fontSize = 9.sp, color = Muted)\n                Text("今开→现 ${openTrack?.let { String.format("%+.2f%%", it) } ?: "—"}", fontSize = 9.sp, color = openTrack?.let(::pnl) ?: Muted)\n                Text("信号收盘→现 ${liveFromSignalClose?.let { String.format("%+.2f%%", it) } ?: "—"}", fontSize = 9.sp, color = liveFromSignalClose?.let(::pnl) ?: Muted)\n            }\n            val hi=q?.high; val lo=q?.low\n            val range=if (hi != null && lo != null && lo > 0) (hi / lo - 1.0) * 100.0 else null\n            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {\n                Text("当日高 ${hi?.let { String.format("%.2f", it) } ?: "—"}", fontSize = 9.sp, color = Muted)\n                Text("当日低 ${lo?.let { String.format("%.2f", it) } ?: "—"}", fontSize = 9.sp, color = Muted)\n                Text("低→高 ${range?.let { String.format("%.2f%%", it) } ?: "—"}", fontSize = 9.sp, color = Muted)\n            }\n            Text("入池收盘价 ${selection?.let { String.format("%.2f", it) } ?: "—"}；‘低→高’是理论区间，不等同可实现交易收益。", fontSize = 8.sp, color = Muted)\n        }\n    }\n}\n\n'''
s=re.sub(pattern,replacement,s,flags=re.S)

# Trade-plan panel belongs in Pools page after quote freshness badge.
needle='''        item {\n            LiveBadge("Pool Quotes", freshnessLabel(now, quoteOkAt, 15000, "LIVE", "STALE"), marketStateOk(now, quoteOkAt), Modifier.fillMaxWidth())\n        }'''
if needle in s and 'TradePlanPanel(codes.toSet())' not in s:
    s=s.replace(needle,needle+'\n        item { TradePlanPanel(codes.toSet()) }',1)

# Reference tracking: display it, but keep audit warning and leaderboard exclusion semantics.
s=s.replace('''if (s.performanceEligible) item { PerformanceCard("${poolTitle(pool)} 后续表现", s.poolPerformance[pool]) } else item { AuditPerformanceBlocked() }''','''item { PerformanceCard("${poolTitle(pool)} 后续表现", s.poolPerformance[pool]) }\n        if (!s.performanceEligible) item { Notice("该批次收益为参考 Tracking：可以看实际后续走势，但不计入策略胜率/Alpha总榜。") }''')
s=s.replace('''if (snap.performanceEligible) item { PerformanceCard("${poolTitle(pool)} 后续跟踪", snap.poolPerformance[pool]) } else item { AuditPerformanceBlocked() }''','''item { PerformanceCard("${poolTitle(pool)} 后续跟踪", snap.poolPerformance[pool]) }\n        if (!snap.performanceEligible) item { Notice("该批次为参考 Tracking，不进入策略总成绩；数值本身仍按可验证入场价计算。") }''')
s=s.replace('''if (s.performanceEligible) TrackingStrip(perf) else Text("旧版未验证 · 收益仅留档，不计入策略统计", fontSize = 9.sp, color = Amber)''','''if (perf != null && perf.length() > 0) TrackingStrip(perf) else Text("跟踪尚未成熟", fontSize = 9.sp, color = Muted)\n            if (!s.performanceEligible) Text("参考Tracking · 不计入策略统计", fontSize = 8.sp, color = Amber)''')

# Helpers.
marker='''fun breadth(b: Board): Double {'''
helper='''fun officialSectorNames(s: Snapshot): List<String> = if (s.mainlines.isNotEmpty()) s.mainlines else s.selectedSectorNames\n\n'''
if marker in s and 'fun officialSectorNames(' not in s:
    s=s.replace(marker,helper+marker,1)

p.write_text(s,encoding='utf-8')

g=Path('app/build.gradle.kts')
gs=g.read_text(encoding='utf-8')
gs=gs.replace('versionCode = 19','versionCode = 20')
gs=gs.replace('versionName = "1.8.0"','versionName = "1.9.0"')
g.write_text(gs,encoding='utf-8')
