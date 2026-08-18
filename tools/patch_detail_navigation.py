from pathlib import Path

p = Path('app/src/main/java/com/rui/astockstrategy/v6/V6Activity.kt')
s = p.read_text(encoding='utf-8')

# Observe global detail navigation state in the root composable.
needle = '''    val preview = remember(industries, concepts) { makePreview((industries + concepts).distinctBy { it.code }) }\n'''
repl = needle + '''    val detailSector = DetailNav.sector\n    val detailStock = DetailNav.stockCode\n'''
if 'val detailSector = DetailNav.sector' not in s:
    if needle not in s:
        raise SystemExit('detail state insertion point not found')
    s = s.replace(needle, repl, 1)

# Bottom navigation exits any open detail page.
old = '''                            onClick = {\n                                tab = item\n                                if (item != Tab.HISTORY) selectedDate = null\n                            },'''
new = '''                            onClick = {\n                                DetailNav.reset()\n                                tab = item\n                                if (item != Tab.HISTORY) selectedDate = null\n                            },'''
if old in s:
    s = s.replace(old, new, 1)

# Detail pages take precedence over the five root tabs.
old = '''                when (tab) {\n                    Tab.TODAY -> TodayScreen(active, preview, quotes, tick, quoteOkAt, boardOkAt)\n                    Tab.MARKET -> MarketScreen(quotes, industries, concepts, tick, quoteOkAt, boardOkAt, quoteError, boardError)\n                    Tab.MAINLINE -> MainlineScreen(active, preview, tick, boardOkAt)\n                    Tab.POOLS -> PoolsScreen(active, quotes, tick, quoteOkAt)\n                    Tab.HISTORY -> HistoryScreen(snapshots, active, quotes, selectedDate) { selectedDate = it }\n                }'''
new = '''                when {\n                    detailStock != null -> {\n                        val detailSnapshot = DetailNav.stockDate?.let { d -> snapshots.firstOrNull { it.date == d } } ?: active\n                        StockDetailScreen(detailStock, detailSnapshot, quotes[symbol(detailStock)]) { DetailNav.back() }\n                    }\n                    detailSector != null -> {\n                        val detailSnapshot = detailSector.date?.let { d -> snapshots.firstOrNull { it.date == d } } ?: active\n                        SectorDetailScreen(detailSector, detailSnapshot) { DetailNav.back() }\n                    }\n                    else -> when (tab) {\n                        Tab.TODAY -> TodayScreen(active, preview, quotes, tick, quoteOkAt, boardOkAt)\n                        Tab.MARKET -> MarketScreen(quotes, industries, concepts, tick, quoteOkAt, boardOkAt, quoteError, boardError)\n                        Tab.MAINLINE -> MainlineScreen(active, preview, tick, boardOkAt)\n                        Tab.POOLS -> PoolsScreen(active, quotes, tick, quoteOkAt)\n                        Tab.HISTORY -> HistoryScreen(snapshots, active, quotes, selectedDate) { selectedDate = it }\n                    }\n                }'''
if 'detailStock != null ->' not in s:
    if old not in s:
        raise SystemExit('root tab switch insertion point not found')
    s = s.replace(old, new, 1)

# Official mainline cards open the frozen sector detail for the same cohort date.
old = '''                items(s.mainlines) { name ->\n                    CardBlock {\n                        Text(name, fontWeight = FontWeight.Bold)\n                        Text("冻结于 ${s.date}", fontSize = 10.sp, color = Muted)\n                    }\n                }'''
new = '''                items(s.mainlines) { name ->\n                    Surface(\n                        modifier = Modifier.fillMaxWidth().clickable { DetailNav.openSectorName(name, s.date) },\n                        color = Color.White,\n                        shape = RoundedCornerShape(16.dp)\n                    ) {\n                        Column(Modifier.fillMaxWidth().padding(13.dp)) {\n                            Text(name, fontWeight = FontWeight.Bold)\n                            Text("冻结于 ${s.date} · 点开查看趋势、资金、结构和成分股", fontSize = 10.sp, color = Muted)\n                        }\n                    }\n                }'''
if old in s:
    s = s.replace(old, new, 1)

# Intraday/close preview sector cards are clickable too.
old = '''fun PreviewRow(p: PreviewSector) {\n    Card(shape = RoundedCornerShape(16.dp)) {'''
new = '''fun PreviewRow(p: PreviewSector) {\n    Card(Modifier.fillMaxWidth().clickable { DetailNav.openSector(p.board) }, shape = RoundedCornerShape(16.dp)) {'''
if old in s:
    s = s.replace(old, new, 1)

old = '''fun PreviewRadar(p: PreviewSector) {\n    Card(shape = RoundedCornerShape(16.dp)) {'''
new = '''fun PreviewRadar(p: PreviewSector) {\n    Card(Modifier.fillMaxWidth().clickable { DetailNav.openSector(p.board) }, shape = RoundedCornerShape(16.dp)) {'''
if old in s:
    s = s.replace(old, new, 1)

# Pool and history stock rows open the stock strategy explanation page.
old = '''fun StockLiveRow(code: String, s: Snapshot, q: Quote?) {\n    val meta = s.stocks[code]\n    Card(shape = RoundedCornerShape(15.dp)) {'''
new = '''fun StockLiveRow(code: String, s: Snapshot, q: Quote?) {\n    val meta = s.stocks[code]\n    Card(Modifier.fillMaxWidth().clickable { DetailNav.openStock(code, s.date) }, shape = RoundedCornerShape(15.dp)) {'''
if old in s:
    s = s.replace(old, new, 1)

old = '''fun HistoryStockRow(code: String, s: Snapshot, q: Quote?) {\n    val meta = s.stocks[code]\n    val perf = s.stockPerformance[code]\n    Card(shape = RoundedCornerShape(15.dp)) {'''
new = '''fun HistoryStockRow(code: String, s: Snapshot, q: Quote?) {\n    val meta = s.stocks[code]\n    val perf = s.stockPerformance[code]\n    Card(Modifier.fillMaxWidth().clickable { DetailNav.openStock(code, s.date) }, shape = RoundedCornerShape(15.dp)) {'''
if old in s:
    s = s.replace(old, new, 1)

# Heatmap tiles open sector detail.
old = '''    Card(modifier, colors = CardDefaults.cardColors(containerColor = bg), shape = RoundedCornerShape(14.dp)) {'''
new = '''    Card(modifier.clickable { DetailNav.openSector(b) }, colors = CardDefaults.cardColors(containerColor = bg), shape = RoundedCornerShape(14.dp)) {'''
if old in s:
    s = s.replace(old, new, 1)

# Small affordance hints in cards.
s = s.replace('Text("$code · ${meta?.sector ?: "—"}", fontSize = 10.sp, color = Muted)', 'Text("$code · ${meta?.sector ?: "—"} · 点开详情", fontSize = 10.sp, color = Muted)')
s = s.replace('Text(b.flow?.let { "资金 ${signedMoney(it)}" } ?: "资金 —", fontSize = 9.sp, color = Muted, maxLines = 1)', 'Text(b.flow?.let { "资金 ${signedMoney(it)} · 点开详情" } ?: "资金 — · 点开详情", fontSize = 9.sp, color = Muted, maxLines = 1)')

p.write_text(s, encoding='utf-8')

# Upgrade version after the base v1 patch has run.
g = Path('app/build.gradle.kts')
gs = g.read_text(encoding='utf-8')
gs = gs.replace('versionCode = 11', 'versionCode = 12')
gs = gs.replace('versionName = "1.0.0"', 'versionName = "1.1.0"')
g.write_text(gs, encoding='utf-8')
