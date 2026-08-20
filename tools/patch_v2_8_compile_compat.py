from pathlib import Path

p = Path('app/src/main/java/com/rui/astockstrategy/v6/V6Activity.kt')
if not p.exists():
    raise SystemExit('V6Activity.kt missing')

s = p.read_text(encoding='utf-8')
# A previous display-localization patch translated only the local variable declaration
# but correctly kept PreviewSector.flowScore as an internal protocol/code identifier.
# Restore the local identifier; this does not change any user-visible Chinese wording.
s = s.replace('val flow评分 =', 'val flowScore =')

if 'val flow评分 =' in s:
    raise SystemExit('localized internal flow variable still present')
if 'val flowScore =' not in s:
    raise SystemExit('flowScore local declaration not found after compatibility fix')

p.write_text(s, encoding='utf-8')
print('v2.8 compile compatibility fixed: internal flowScore identifier restored')
