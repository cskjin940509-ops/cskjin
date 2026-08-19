from pathlib import Path

p = Path('app/src/main/java/com/rui/astockstrategy/v6/V6Activity.kt')
s = p.read_text(encoding='utf-8')

# Run after the rolling-tail and Chinese UI patches. Put the execution assistant
# immediately below the tail panel so live decision support is visible on Home.
if 'ExecutionPanel()' not in s:
    needle = 'item { TailDecisionPanel() }'
    if needle in s:
        s = s.replace(needle, needle + '\n        item { ExecutionPanel() }', 1)
    else:
        # Fallback for builds where tail insertion changed formatting.
        needle = 'StatusCard(now, quoteOkAt, boardOkAt, s)\n        }'
        if needle not in s:
            raise SystemExit('ExecutionPanel insertion point not found')
        s = s.replace(needle, needle + '\n        item { ExecutionPanel() }', 1)

p.write_text(s, encoding='utf-8')

# Keep the new file independent from private symbols in V6Activity.kt.
e = Path('app/src/main/java/com/rui/astockstrategy/v6/ExecutionPanel.kt')
es = e.read_text(encoding='utf-8')
es = es.replace('LocalDate.now(CnZone)', 'LocalDate.now(java.time.ZoneId.of("Asia/Shanghai"))')
es = es.replace('java.time.LocalTime.now(CnZone)', 'java.time.LocalTime.now(java.time.ZoneId.of("Asia/Shanghai"))')
es = es.replace(
    'stocksObj.keys().forEachRemaining(codes::add)',
    'stocksObj.keys().asSequence().forEach { codes.add(it) }'
)
e.write_text(es, encoding='utf-8')

g = Path('app/build.gradle.kts')
gs = g.read_text(encoding='utf-8')
gs = gs.replace('versionCode = 23', 'versionCode = 24')
gs = gs.replace('versionName = "2.1.1"', 'versionName = "2.2.0"')
g.write_text(gs, encoding='utf-8')
