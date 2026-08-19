from pathlib import Path

p = Path('app/src/main/java/com/rui/astockstrategy/v6/V6Activity.kt')
s = p.read_text(encoding='utf-8')
needle = '''        item {\n            StatusCard(now, quoteOkAt, boardOkAt, s)\n        }'''
repl = '''        item {\n            StatusCard(now, quoteOkAt, boardOkAt, s)\n        }\n        item { TailDecisionPanel() }'''
if 'TailDecisionPanel()' not in s:
    if needle not in s:
        raise SystemExit('TailDecision insertion point not found')
    s = s.replace(needle, repl, 1)
p.write_text(s, encoding='utf-8')

g = Path('app/build.gradle.kts')
gs = g.read_text(encoding='utf-8')
gs = gs.replace('versionCode = 17', 'versionCode = 18')
gs = gs.replace('versionName = "1.6.0"', 'versionName = "1.7.0"')
g.write_text(gs, encoding='utf-8')
