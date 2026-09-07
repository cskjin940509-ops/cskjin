from pathlib import Path
import re
r=Path(__file__).resolve().parents[1]
v=dict(x.split('=',1) for x in (r/'version.properties').read_text().splitlines() if '=' in x)
assert re.fullmatch(r'\d+\.\d+\.\d+',v['versionName'])
assert int(v['versionCode']) >= 47
for name in ('app','desktop'): assert 'version.properties' in (r/name/'build.gradle.kts').read_text()
assert '../app/src/main/java/com/rui/astockstrategy/v6' in (r/'desktop/build.gradle.kts').read_text()
for p in (r/'app/src/main/java/com/rui/astockstrategy/v6').glob('*.kt'):
 assert not re.search(r'^import android\.',p.read_text(),re.M),p
 assert 'LocalContext' not in p.read_text(),p
assert not list((r/'desktop/src').rglob('V46StrategyResearch.kt'))
print('PASS shared screens, backend client, and version '+v['versionName'])
