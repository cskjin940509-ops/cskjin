from pathlib import Path
import re

p = Path('app/src/main/java/com/rui/astockstrategy/v6/V6Activity.kt')
s = p.read_text(encoding='utf-8')

# Preserve the frozen signal-day move in the app model so Official still has
# useful same-day facts even when the phone cannot reach the live quote source.
s = s.replace(
    '    val selectionPrice: Double?,\n    val confidence: String?\n)',
    '    val selectionPrice: Double?,\n    val dayChangePct: Double?,\n    val confidence: String?\n)',
    1,
)

# Official may have selected sectors while no sector crossed the stricter
# confirmed-mainline threshold. Keep those two semantics separate in the UI.
s = s.replace(
    '    val mainlines: List<String>,\n    val pools: Map<String, List<String>>,',
    '    val mainlines: List<String>,\n    val selectedSectors: List<String>,\n    val pools: Map<String, List<String>>,',
    1,
)

s = s.replace(
    '                    num(x, "selectionPrice"),\n                    x.optString("confidence").takeIf { it.isNotBlank() }',
    '                    num(x, "selectionPrice"),\n                    num(x, "changePct"),\n                    x.optString("confidence").takeIf { it.isNotBlank() }',
    1,
)

s = s.replace(
    '            mainlines = arrStrings(o.optJSONArray("mainlines")),\n            pools = pools,',
    '            mainlines = arrStrings(o.optJSONArray("mainlines")),\n            selectedSectors = arrObjectNames(o.optJSONArray("selectedSectors")),\n            pools = pools,',
    1,
)

# Avoid stale raw.githubusercontent CDN snapshots after an Official commit.
s = s.replace(
    '        val a = JSONArray(getText(SNAP))',
    '        val a = JSONArray(getText("$SNAP?t=${System.currentTimeMillis()}"))',
    1,
)

# Parser helper for selectedSectors [{name: ...}].
marker = '''    private fun arrStrings(a: JSONArray?): List<String> {'''
helper = '''    private fun arrObjectNames(a: JSONArray?): List<String> {\n        if (a == null) return emptyList()\n        return (0 until a.length()).mapNotNull { i ->\n            a.optJSONObject(i)?.optString("name")?.takeIf { it.isNotBlank() }\n        }\n    }\n\n'''
if 'private fun arrObjectNames' not in s:
    s = s.replace(marker, helper + marker, 1)

# Main status cards should show the actual formal sector set even when the
# stricter confirmedMainline list is empty.
s = s.replace(
    'Key("主线", s.mainlines.joinToString(" / ").ifBlank { "—" })',
    'Key(if (s.mainlines.isNotEmpty()) "确认主线" else "正式筛选板块", formalSectorNames(s).joinToString(" / ").ifBlank { "—" })'
)
s = s.replace(
    'Key("主线", snap.mainlines.joinToString(" / ").ifBlank { "—" })',
    'Key(if (snap.mainlines.isNotEmpty()) "确认主线" else "正式筛选板块", formalSectorNames(snap).joinToString(" / ").ifBlank { "—" })'
)

# Official mainline tab: no longer render an empty page when selected sectors
# exist but none reached the stricter confirmed-mainline threshold.
old = '''                if (s.mainlines.isEmpty()) item { EmptyCard("该日无主线") }\n                items(s.mainlines) { name ->\n                    CardBlock {\n                        Text(name, fontWeight = FontWeight.Bold)\n                        Text("冻结于 ${s.date}", fontSize = 10.sp, color = Muted)\n                    }\n                }'''
new = '''                val formal = formalSectorNames(s)\n                if (formal.isEmpty()) item { EmptyCard("该日没有达到正式筛选阈值的板块") }\n                if (s.mainlines.isEmpty() && formal.isNotEmpty()) {\n                    item { Notice("当天没有板块达到更严格的“确认主线”阈值；以下为实际用于正式股票筛选的收盘板块，不会伪装成确认主线。") }\n                }\n                items(formal) { name ->\n                    CardBlock {\n                        Text(name, fontWeight = FontWeight.Bold)\n                        Text(if (s.mainlines.isNotEmpty()) "确认主线 · 冻结于 ${s.date}" else "正式筛选板块 · 冻结于 ${s.date}", fontSize = 10.sp, color = Muted)\n                    }\n                }'''
if old in s:
    s = s.replace(old, new, 1)

# Replace current-stock row. The signal-day move is a market fact, not strategy
# return; strategy tracking starts at the next tradable open and is shown apart.
pattern = re.compile(r'@Composable\nfun StockLiveRow\(code: String, s: Snapshot, q: Quote\?\) \{.*?\n\}\n\n@Composable\nfun HistoryStockRow', re.S)
replacement = '''@Composable\nfun StockLiveRow(code: String, s: Snapshot, q: Quote?) {\n    val meta = s.stocks[code]\n    val perf = s.stockPerformance[code]\n    val selection = meta?.selectionPrice\n    val shownPrice = q?.price ?: selection\n    val dayMove = q?.change ?: meta?.dayChangePct\n    val tracking = jsonReturn(perf?.optJSONObject("current"))\n    Card(shape = RoundedCornerShape(15.dp)) {\n        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {\n            Row {\n                Column(Modifier.weight(1f)) {\n                    Text(meta?.name ?: q?.name ?: code, fontWeight = FontWeight.Bold)\n                    Text("$code · ${meta?.sector ?: "—"}", fontSize = 10.sp, color = Muted)\n                }\n                Column(horizontalAlignment = Alignment.End) {\n                    Text(shownPrice?.let { String.format("%.2f", it) } ?: "—", fontWeight = FontWeight.Bold)\n                    Text(dayMove?.let(::pct) ?: "—", color = dayMove?.let(::pnl) ?: Muted, fontSize = 11.sp)\n                }\n            }\n            Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {\n                Text("收盘入池价 ${selection?.let { String.format("%.2f", it) } ?: "—"}", fontSize = 10.sp, color = Muted)\n                Text("当日涨跌 ${meta?.dayChangePct?.let(::pct) ?: dayMove?.let(::pct) ?: "—"}", fontSize = 10.sp, color = (meta?.dayChangePct ?: dayMove)?.let(::pnl) ?: Muted)\n            }\n            Text(\n                tracking?.let { "策略跟踪至今 ${pct(it * 100.0)}" }\n                    ?: "策略跟踪：等待信号后下一交易日可成交开盘",\n                fontSize = 10.sp,\n                color = tracking?.let { pnl(it) } ?: Muted\n            )\n        }\n    }\n}\n\n@Composable\nfun HistoryStockRow'''
s, n = pattern.subn(replacement, s, count=1)
if n != 1:
    raise SystemExit('StockLiveRow replacement failed')

# Replace history row so reference tracking is visible even when the cohort is
# excluded from factor scorecards. The warning remains explicit.
pattern = re.compile(r'@Composable\nfun HistoryStockRow\(code: String, s: Snapshot, q: Quote\?\) \{.*?\n\}\n\n@Composable\nfun IndexCard', re.S)
replacement = '''@Composable\nfun HistoryStockRow(code: String, s: Snapshot, q: Quote?) {\n    val meta = s.stocks[code]\n    val perf = s.stockPerformance[code]\n    val current = jsonReturn(perf?.optJSONObject("current"))\n    Card(shape = RoundedCornerShape(15.dp)) {\n        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {\n            Row {\n                Column(Modifier.weight(1f)) {\n                    Text(meta?.name ?: q?.name ?: code, fontWeight = FontWeight.Bold)\n                    Text("$code · ${meta?.sector ?: "—"}", fontSize = 10.sp, color = Muted)\n                }\n                Text(s.pools.filterValues { code in it }.keys.sorted().joinToString(" "), fontSize = 10.sp, color = Blue)\n            }\n            Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {\n                Text("信号日 ${meta?.dayChangePct?.let(::pct) ?: "—"}", fontSize = 10.sp, color = meta?.dayChangePct?.let(::pnl) ?: Muted)\n                Text("入池价 ${meta?.selectionPrice?.let { String.format("%.2f", it) } ?: "—"}", fontSize = 10.sp, color = Muted)\n                Text("跟踪 ${current?.let { pct(it * 100.0) } ?: "—"}", fontSize = 10.sp, color = current?.let(::pnl) ?: Muted)\n            }\n            if (perf != null && perf.length() > 0) {\n                TrackingStrip(perf)\n                if (!s.performanceEligible) Text("参考跟踪 · 该批次不进入胜率/Alpha/因子成绩统计", fontSize = 9.sp, color = Amber)\n            } else {\n                Text("Forward Tracking（前瞻跟踪）尚未成熟；从信号后下一交易日可成交开盘起算。", fontSize = 9.sp, color = Muted)\n            }\n        }\n    }\n}\n\n@Composable\nfun IndexCard'''
s, n = pattern.subn(replacement, s, count=1)
if n != 1:
    raise SystemExit('HistoryStockRow replacement failed')

# Pool screen: always show frozen signal-day facts immediately, then show
# forward tracking when mature. Reference-only cohorts are visible but labeled.
s = s.replace(
    '        item {\n            LiveBadge("Pool Quotes", freshnessLabel(now, quoteOkAt, 15000, "实时", "已过期"), marketStateOk(now, quoteOkAt), Modifier.fillMaxWidth())\n        }',
    '        item {\n            LiveBadge("Pool Quotes", freshnessLabel(now, quoteOkAt, 15000, "实时", "已过期"), marketStateOk(now, quoteOkAt), Modifier.fillMaxWidth())\n        }\n        item { PoolReturnSummary(s, pool) }',
    1,
)
# Fallback for older label if terminology patch did not transform it exactly.
s = s.replace(
    '        item {\n            LiveBadge("Pool Quotes", freshnessLabel(now, quoteOkAt, 15000, "LIVE", "STALE"), marketStateOk(now, quoteOkAt), Modifier.fillMaxWidth())\n        }',
    '        item {\n            LiveBadge("Pool Quotes", freshnessLabel(now, quoteOkAt, 15000, "LIVE", "STALE"), marketStateOk(now, quoteOkAt), Modifier.fillMaxWidth())\n        }\n        item { PoolReturnSummary(s, pool) }',
    1,
)

s = s.replace(
    'if (s.performanceEligible) item { PerformanceCard("${poolTitle(pool)} 后续表现", s.poolPerformance[pool]) } else item { AuditPerformanceBlocked() }',
    'item { PerformanceCard("${poolTitle(pool)} 后续表现", s.poolPerformance[pool]) }; if (!s.performanceEligible && (s.poolPerformance[pool]?.length() ?: 0) > 0) item { Notice("该批次跟踪仅作价格路径参考，不进入胜率、Alpha或因子有效性统计。") }'
)
s = s.replace(
    'if (snap.performanceEligible) item { PerformanceCard("${poolTitle(pool)} 后续跟踪", snap.poolPerformance[pool]) } else item { AuditPerformanceBlocked() }',
    'item { PoolReturnSummary(snap, pool) }; item { PerformanceCard("${poolTitle(pool)} 后续跟踪", snap.poolPerformance[pool]) }; if (!snap.performanceEligible && (snap.poolPerformance[pool]?.length() ?: 0) > 0) item { Notice("参考跟踪已显示，但该批次仍不进入策略成绩统计。") }'
)

# Helpers before audit/performance helpers.
marker = 'fun snapshotAuditLabel(s: Snapshot): String = when (s.auditStatus) {'
helpers = '''fun formalSectorNames(s: Snapshot): List<String> = if (s.mainlines.isNotEmpty()) s.mainlines else s.selectedSectors\n\nfun jsonReturn(o: JSONObject?): Double? {\n    if (o == null) return null\n    val v = o.opt("return")\n    return when (v) {\n        null, JSONObject.NULL -> null\n        is Number -> v.toDouble()\n        else -> v.toString().toDoubleOrNull()\n    }\n}\n\n@Composable\nfun PoolReturnSummary(s: Snapshot, pool: String) {\n    val codes = s.pools[pool].orEmpty()\n    val moves = codes.mapNotNull { s.stocks[it]?.dayChangePct }\n    val signalDayAvg = moves.takeIf { it.isNotEmpty() }?.average()\n    val tracking = jsonReturn(s.poolPerformance[pool]?.optJSONObject("current"))\n    CardBlock {\n        Text("收益状态", fontWeight = FontWeight.Bold)\n        Key("信号日等权涨跌", signalDayAvg?.let(::pct) ?: "—")\n        Key("策略跟踪至今", tracking?.let { pct(it * 100.0) } ?: "等待下一交易日可成交开盘")\n        Text("信号日涨跌是入池前当天已经发生的市场表现；策略收益从信号后下一交易日可成交开盘开始，二者不混用。", fontSize = 9.sp, color = Muted)\n    }\n}\n\n'''
if 'fun formalSectorNames(' not in s:
    if marker not in s:
        # Audit patch may be absent in a local debug chain; insert before PerformanceCard.
        marker = '@Composable\nfun PerformanceCard(title: String, p: JSONObject?) {'
    s = s.replace(marker, helpers + marker, 1)

p.write_text(s, encoding='utf-8')

# v1.9 after rolling-tail v1.8.
g = Path('app/build.gradle.kts')
gs = g.read_text(encoding='utf-8')
gs = gs.replace('versionCode = 19', 'versionCode = 20')
gs = gs.replace('versionName = "1.8.0"', 'versionName = "1.9.0"')
g.write_text(gs, encoding='utf-8')
