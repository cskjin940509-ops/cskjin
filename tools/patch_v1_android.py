from pathlib import Path

# Remove legacy activities that conflict with the current app entrypoint.
for f in [
    'app/src/main/java/com/rui/astockstrategy/V04Activity.kt',
    'app/src/main/java/com/rui/astockstrategy/v5/V5Activity.kt',
]:
    Path(f).unlink(missing_ok=True)

p = Path('app/src/main/java/com/rui/astockstrategy/v6/V6Activity.kt')
s = p.read_text(encoding='utf-8')

# Historical market replay entry.
needle = '''        item { CardBlock { Key("日期", snap.date); Key("状态", snap.status); Key("Regime", snap.regime); Key("主线", snap.mainlines.joinToString(" / ").ifBlank { "—" }) } }'''
repl = '''        item { CardBlock { Key("日期", snap.date); Key("状态", zhStatus(snap.status)); Key("市场状态", snap.regime); Key("主线", snap.mainlines.joinToString(" / ").ifBlank { "—" }) } }\n        item { HistoricalMarketReplay(snap.date) }\n        item { Title("策略回顾") }'''
if 'HistoricalMarketReplay(snap.date)' not in s:
    if needle not in s:
        raise SystemExit('history insertion point not found')
    s = s.replace(needle, repl, 1)

# Post-close facts first, strategy later.
today_old = '''        item {\n            StatusCard(now, quoteOkAt, boardOkAt, s)\n        }\n        item { Title("Intraday Preview（盘中预览）") }\n        item {\n            Notice("盘中只用当前可实时取得的公开行情生成主线候选，不冒充正式 B1/B2/B3/B4。正式 Daily Cohort 收盘后另行冻结。")\n        }'''
today_new = '''        item {\n            StatusCard(now, quoteOkAt, boardOkAt, s)\n        }\n        if (!marketOpenNow()) {\n            item { PostCloseDashboard(quotes, preview, s) }\n            item { Title("收盘主线预览") }\n            item { Notice("收盘后先展示当天已核验的指数、板块和资金事实；正式每日股票池尚未完成时显示“策略计算中”，不使用昨日名单冒充今天结果。") }\n        } else {\n            item { Title("盘中主线预览") }\n            item { Notice("盘中主线仅使用当前可取得的实时行情计算；两融、ETF申赎等非实时因子不会伪装成实时数据。") }\n        }'''
if 'PostCloseDashboard(quotes, preview, s)' not in s:
    if today_old not in s:
        raise SystemExit('today insertion point not found')
    s = s.replace(today_old, today_new, 1)

# Direct source first; GitHub gateway fallback second.
s = s.replace('''            runCatching {\n                val ind = DataApi.fetchBoards("industry")\n                val con = DataApi.fetchBoards("concept")\n                ind to con\n            }''', '''            runCatching { ResilientDataApi.fetchBoardsPair() }''')
s = s.replace('runCatching { DataApi.fetchQuotes(symbols) }', 'runCatching { ResilientDataApi.fetchQuotes(symbols) }')

# Data source diagnostics.
status_line = '''            Key("盘中主线", if (marketOpenNow()) "LIVE Preview" else "Close Preview")'''
status_new = '''            Key("盘中主线", if (marketOpenNow()) "实时预览" else "收盘预览")\n            Key("行情来源", ResilientDataApi.quoteSource)\n            Key("板块来源", ResilientDataApi.boardSource)'''
s = s.replace(status_line, status_new)

# Chinese financial terminology in user-facing UI only.
for a, b in {
    'Data Status（数据状态）': '数据状态',
    '实时行情和策略快照分开显示': '实时行情、板块数据与策略快照分层显示',
    'Intraday Preview（盘中预览）': '盘中主线预览',
    'Latest Official / Snapshot': '最新正式策略快照',
    'B4 Live Monitor（实时跟踪）': 'B4组合实时跟踪',
    'Mainline Preview': '主线预览',
    'Momentum': '动量强度',
    'Breadth': '上涨扩散度',
    'Flow': '资金强度',
    'Official Snapshot': '正式策略快照',
    'Market Alpha': '市场超额收益',
    'Industry Alpha': '行业超额收益',
    'MFE': '最大有利涨幅',
    'MAE': '最大不利跌幅',
    'Trend Survival': '趋势存续期',
}.items():
    s = s.replace(a, b)

s = s.replace('item { Title("实时${type}热力图") }', 'item { Title(if (marketOpenNow()) "实时${type}热力图" else "收盘${type}热力图") }')

# Validate provider timestamp; never expose raw dirty values such as 161495.
s = s.replace('quoteTime = f.getOrNull(30)', 'quoteTime = normalizeQuoteTime(f.getOrNull(30))')
marker = 'fun breadth(b: Board): Double {'
helper = '''fun normalizeQuoteTime(raw: String?): String? {\n    val v = raw?.trim().orEmpty()\n    if (!Regex("\\\\d{14}").matches(v)) return null\n    return runCatching {\n        LocalDateTime.parse(v, DateTimeFormatter.ofPattern("yyyyMMddHHmmss"))\n            .format(DateTimeFormatter.ofPattern("HH:mm:ss"))\n    }.getOrNull()\n}\n\nfun zhStatus(v: String?): String = when (v?.lowercase()) {\n    "official" -> "正式"\n    "preview" -> "预览"\n    else -> v ?: "未知"\n}\n\n'''
if 'fun normalizeQuoteTime' not in s:
    if marker not in s:
        raise SystemExit('breadth helper marker not found')
    s = s.replace(marker, helper + marker, 1)

s = s.replace('return "行情 OFFLINE"', 'return "行情未连接"')
s = s.replace('return "行情 STALE ${age}s"', 'return "行情已过期 ${age}秒"')
s = s.replace('"行情 LIVE ${age}s"', '"行情实时 ${age}秒"')
s = s.replace('"行情 CLOSED ${quoteTime?.takeLast(6) ?: "已收盘"}"', '"行情已收盘 ${quoteTime ?: ""}"')
s = s.replace('"LIVE", "STALE"', '"实时", "已过期"')
s = s.replace('return "OFFLINE"', 'return "未连接"')
s = s.replace('q?.quoteTime?.let { "行情 $it" }', 'q?.quoteTime?.let { "行情时间 $it" }')
s = s.replace('"无时间戳"', '"行情时间不可用"')
s = s.replace('EmptyCard("尚未读取到正式策略快照")', 'EmptyCard("正式策略尚未同步；行情与板块数据仍独立可用")')
s = s.replace('EmptyCard("暂无 Official Snapshot")', 'EmptyCard("正式策略尚未同步")')

# Improve direct public-source compatibility on Android.
old = '''        c.setRequestProperty("User-Agent", "Mozilla/5.0 AStockStrategy/0.6")\n        c.setRequestProperty("Cache-Control", "no-cache")'''
new = '''        c.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 Chrome/140 Mobile Safari/537.36")\n        c.setRequestProperty("Accept", "*/*")\n        c.setRequestProperty("Cache-Control", "no-cache")\n        if (url.contains("gtimg.cn")) c.setRequestProperty("Referer", "https://gu.qq.com/")\n        if (url.contains("eastmoney.com")) c.setRequestProperty("Referer", "https://quote.eastmoney.com/")'''
s = s.replace(old, new)
p.write_text(s, encoding='utf-8')

# Historical market replay fixes and Chinese terminology.
h = Path('app/src/main/java/com/rui/astockstrategy/v6/HistoricalReplay.kt')
hs = h.read_text(encoding='utf-8')
# Critical Kotlin interpolation fix.
hs = hs.replace('"该日$title热力图尚未冻结/回填。不会显示今天的实时板块数据。"', '"该日${title}热力图尚未冻结/回填。不会显示今天的实时板块数据。"')
for a, b in {
    'Historical Market Replay（历史市场回放）': '历史市场回放',
    'Backfill（历史回填）': '历史回填',
    'marketSnapshot / boardHeatmap': '市场快照 / 板块热力图',
    'RS20': '20日相对强弱',
    'MTA ': '多周期趋势 ',
}.items():
    hs = hs.replace(a, b)
hs = hs.replace('历史数据读取失败：$error。不会拿当前实时行情冒充历史。', '历史数据源读取失败（$error）。不会拿当前行情冒充历史。')
hs = hs.replace('$date 尚未保存 市场快照 / 板块热力图。后台完成历史回填后这里会自动出现，不需要重装 APK。', '$date 的市场快照和板块热力图尚未同步；后台补齐后会自动出现。')
hs = hs.replace('"该日${title}热力图尚未冻结/回填。不会显示今天的实时板块数据。"', '"该日${title}热力图数据尚未同步，不会拿今天行情冒充历史。"')
h.write_text(hs, encoding='utf-8')

# Post-close screen Chinese terminology.
pc = Path('app/src/main/java/com/rui/astockstrategy/v6/PostCloseDashboard.kt')
ps = pc.read_text(encoding='utf-8')
for a, b in {
    'Post-close Market Snapshot（收盘市场截面）': '收盘市场截面',
    'Official Daily Cohort': '正式每日股票池',
    'Breadth': '上涨扩散度',
    'Score ': '综合强度 ',
    'Confirmed Candidate': '强势候选',
    'Candidate': '候选',
    'Observe': '观察',
}.items():
    ps = ps.replace(a, b)
pc.write_text(ps, encoding='utf-8')

# Version.
g = Path('app/build.gradle.kts')
gs = g.read_text(encoding='utf-8')
gs = gs.replace('versionCode = 7', 'versionCode = 11').replace('versionName = "0.7.0"', 'versionName = "1.0.0"')
g.write_text(gs, encoding='utf-8')
