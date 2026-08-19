from pathlib import Path

p = Path('app/src/main/java/com/rui/astockstrategy/v6/V6Activity.kt')
s = p.read_text(encoding='utf-8')

needle = '''            Key("行情来源", ResilientDataApi.quoteSource)\n            Key("板块来源", ResilientDataApi.boardSource)'''
repl = needle + '''\n            YunaiGatewayStatusLine()'''
if 'YunaiGatewayStatusLine()' not in s:
    if needle not in s:
        raise SystemExit('Yunai status insertion point not found')
    s = s.replace(needle, repl, 1)

# Version is applied after v1.2 pairwise patch.
g = Path('app/build.gradle.kts')
gs = g.read_text(encoding='utf-8')
gs = gs.replace('versionCode = 13', 'versionCode = 14')
gs = gs.replace('versionName = "1.2.0"', 'versionName = "1.3.0"')
g.write_text(gs, encoding='utf-8')

p.write_text(s, encoding='utf-8')
