from pathlib import Path

# App live quote mapping: BSE 8/9-prefix securities must use bj, not sz.
p = Path('app/src/main/java/com/rui/astockstrategy/v6/V6Activity.kt')
s = p.read_text(encoding='utf-8')
old = '''fun symbol(code: String): String = when {\n    code.startsWith("6") || code.startsWith("68") -> "sh$code"\n    else -> "sz$code"\n}'''
new = '''fun symbol(code: String): String = when {\n    code.startsWith("8") || code.startsWith("9") -> "bj$code"\n    code.startsWith("5") || code.startsWith("6") -> "sh$code"\n    else -> "sz$code"\n}'''
if old not in s:
    raise SystemExit('symbol mapping block not found')
s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')

# Eastmoney BSE uses market id 0 (e.g. 0.920087), not market id 1.
d = Path('app/src/main/java/com/rui/astockstrategy/v6/DetailScreens.kt')
ds = d.read_text(encoding='utf-8')
old = 'private fun stockSecid(code: String): String = (if (code.startsWith("5") || code.startsWith("6") || code.startsWith("9")) "1." else "0.") + code'
new = 'private fun stockSecid(code: String): String = (if (code.startsWith("5") || code.startsWith("6")) "1." else "0.") + code'
if old not in ds:
    raise SystemExit('stockSecid mapping block not found')
ds = ds.replace(old, new, 1)
d.write_text(ds, encoding='utf-8')

# Version v1.6 after v1.5 board failover patch.
g = Path('app/build.gradle.kts')
gs = g.read_text(encoding='utf-8')
gs = gs.replace('versionCode = 16', 'versionCode = 17')
gs = gs.replace('versionName = "1.5.0"', 'versionName = "1.6.0"')
g.write_text(gs, encoding='utf-8')
