from pathlib import Path

# Main pool parser + selectors.
p = Path('app/src/main/java/com/rui/astockstrategy/v6/V6Activity.kt')
s = p.read_text(encoding='utf-8')

s = s.replace(
    'listOf("B0", "B1", "B2", "B3", "B4").associateWith { key -> arrStrings(poolsObj.optJSONArray(key)) }',
    'listOf("B0", "B1", "B2", "B3", "B12", "B13", "B23", "B4").associateWith { key -> arrStrings(poolsObj.optJSONArray(key)) }'
)

old_choice = 'item { Choice(listOf("B0", "B1", "B2", "B3", "B4"), pool) { pool = it } }'
s = s.replace(old_choice, 'item { PoolSelector(pool) { pool = it } }')

s = s.replace(
    'Notice("$pool 名单来自 ${s.date} 的 ${s.status} Daily Cohort；股票价格是 Live Monitor。名单本身不会盘中乱跳。")',
    'Notice("${poolTitle(pool)} 来自 ${s.date} 的 ${zhStatus(s.status)}每日批次；名单本身冻结，价格独立更新。组合池要求对应两个资金因子都正式达标。")'
)
s = s.replace(
    'EmptyCard("该日 $pool 没有达标股票")',
    'EmptyCard("${poolTitle(pool)} 当前为空。若必要资金因子尚未同步或没有共同达标股票，组合池会保持为空。")'
)
s = s.replace(
    'PerformanceCard("$pool 后续表现", s.poolPerformance[pool])',
    'PerformanceCard("${poolTitle(pool)} 后续表现", s.poolPerformance[pool])'
)
s = s.replace(
    'if (codes.isEmpty()) item { EmptyCard("当日 $pool 为空") }',
    'if (codes.isEmpty()) item { EmptyCard("${poolTitle(pool)} 当日为空；历史版本未生成该池或必要因子不足时不会回填假信号。") }'
)
s = s.replace(
    'item { PerformanceCard("$pool Cohort Forward Tracking", snap.poolPerformance[pool]) }',
    'item { PerformanceCard("${poolTitle(pool)} 后续跟踪", snap.poolPerformance[pool]) }'
)

marker = '''@Composable\nfun Choice(items: List<String>, value: String, onChange: (String) -> Unit) {'''
helper = '''fun poolTitle(pool: String): String = when (pool) {\n    "B0" -> "B0 基础池"\n    "B1" -> "B1 两融增强"\n    "B2" -> "B2 ETF资金"\n    "B3" -> "B3 主力资金"\n    "B12" -> "B12 两融+ETF"\n    "B13" -> "B13 两融+主力"\n    "B23" -> "B23 ETF+主力"\n    "B4" -> "B4 三资金/综合确认"\n    else -> pool\n}\n\n@Composable\nfun PoolSelector(value: String, onChange: (String) -> Unit) {\n    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {\n        Text("单因子 / 基础", fontSize = 10.sp, color = Muted, fontWeight = FontWeight.SemiBold)\n        Choice(listOf("B0", "B1", "B2", "B3"), value, onChange)\n        Text("组合确认", fontSize = 10.sp, color = Muted, fontWeight = FontWeight.SemiBold)\n        Choice(listOf("B12", "B13", "B23", "B4"), value, onChange)\n        Text("当前：${poolTitle(value)}", fontSize = 10.sp, color = Blue)\n    }\n}\n\n'''
if 'fun PoolSelector(' not in s:
    if marker not in s:
        raise SystemExit('Choice insertion point not found')
    s = s.replace(marker, helper + marker, 1)

p.write_text(s, encoding='utf-8')

# Stock detail: discover and explain pairwise pools.
d = Path('app/src/main/java/com/rui/astockstrategy/v6/DetailScreens.kt')
ds = d.read_text(encoding='utf-8')
ds = ds.replace(
    'listOf("B0", "B1", "B2", "B3", "B4").forEach { p ->',
    'listOf("B0", "B1", "B2", "B3", "B12", "B13", "B23", "B4").forEach { p ->'
)

ds = ds.replace(
    'Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) { pools.forEach { DetailTag(it, it == "B4") } }',
    'Text("入选池：${pools.joinToString(" / ") { poolTitle(it) }}", color = DetailBlue, fontSize = 10.sp, fontWeight = FontWeight.SemiBold)'
)

old = '''        item { DetailCard { DetailKey("主力净流入", f?.mainNetFlow?.let(::signedMoney) ?: "—"); DetailKey("两融增强 B1", if ("B1" in pools) "已入池" else "—"); DetailKey("ETF增强 B2", if ("B2" in pools) "已入池" else "—"); Text("B1/B2没有正式数据时保持空值，不用其他口径代替。", color = DetailMuted, fontSize = 9.sp) } }'''
new = '''        item {\n            DetailCard {\n                DetailKey("主力净流入", f?.mainNetFlow?.let(::signedMoney) ?: "—")\n                DetailKey("两融增强 B1", if ("B1" in pools) "已入池" else "—")\n                DetailKey("ETF资金 B2", if ("B2" in pools) "已入池" else "—")\n                DetailKey("主力资金 B3", if ("B3" in pools) "已入池" else "—")\n                DetailKey("两融+ETF B12", if ("B12" in pools) "双因子确认" else "—")\n                DetailKey("两融+主力 B13", if ("B13" in pools) "双因子确认" else "—")\n                DetailKey("ETF+主力 B23", if ("B23" in pools) "双因子确认" else "—")\n                DetailKey("三资金/综合 B4", if ("B4" in pools) "综合确认" else "—")\n                Text("组合池只有对应源因子均正式达标才会出现；缺失因子不使用中性分或其他口径补齐。", color = DetailMuted, fontSize = 9.sp)\n            }\n        }'''
if old in ds:
    ds = ds.replace(old, new, 1)

d.write_text(ds, encoding='utf-8')

# Version bump after v1.1 detail patch.
g = Path('app/build.gradle.kts')
gs = g.read_text(encoding='utf-8')
gs = gs.replace('versionCode = 12', 'versionCode = 13')
gs = gs.replace('versionName = "1.1.0"', 'versionName = "1.2.0"')
g.write_text(gs, encoding='utf-8')
