from pathlib import Path

root = Path('app/src/main/java/com/rui/astockstrategy/v6')

# Shared display-only translators. Protocol fields/status values stay untouched.
helper = root / 'V27ChineseDisplay.kt'
helper.write_text(r'''package com.rui.astockstrategy.v6

fun displayStatusZh27(v: String?): String = when (v?.trim()?.lowercase()) {
    null, "" -> "未知"
    "official" -> "正式冻结"
    "preview" -> "盘中预览"
    "tailfinal" -> "尾盘最终"
    "taillive" -> "尾盘滚动"
    "radarlive" -> "全天雷达滚动"
    "radarfinal" -> "全天雷达收盘冻结"
    "ready" -> "已就绪"
    "live" -> "实时"
    "stale" -> "已过期"
    "offline" -> "未连接"
    "closed" -> "已收盘"
    "unknown" -> "未知"
    else -> v ?: "未知"
}

fun displayPoolZh27(v: String): String = when (v) {
    "B0" -> "基础强度池"
    "B1" -> "两融确认池"
    "B2" -> "指数基金申赎确认池"
    "B3" -> "主力资金确认池"
    "B4" -> "综合确认池"
    "B12" -> "两融+指数基金联合池"
    "B13" -> "两融+主力联合池"
    "B23" -> "指数基金+主力联合池"
    "TB0" -> "尾盘基础强度池"
    "TB3" -> "尾盘资金确认池"
    "TailCore" -> "尾盘核心池"
    "EarlyWatch" -> "提前观察池"
    "EarlyEntry" -> "提前介入候选池"
    "Confirming" -> "主线确认中候选池"
    "EstablishedLowChase" -> "已成主线低追高风险池"
    "AvoidChase" -> "禁止追高观察池"
    else -> v
}

fun displayPreviewStateZh27(v: String?): String = when (v) {
    "Confirmed Candidate" -> "确认候选"
    "Candidate" -> "候选"
    "Observe" -> "观察"
    "EMERGING" -> "潜在形成"
    "CONFIRMING" -> "确认中"
    "ESTABLISHED" -> "已成主线"
    "OVERHEATED" -> "过热"
    "FADING" -> "衰退"
    "RADAR" -> "雷达观察"
    else -> displayStatusZh27(v)
}

fun displayHorizonZh27(v: String): String = when (v) {
    "1D" -> "1日"
    "2D" -> "2日"
    "3D" -> "3日"
    "5D" -> "5日"
    "10D" -> "10日"
    "20D" -> "20日"
    "60D" -> "60日"
    else -> v
}

fun displayRegimeZh27(v: String?): String = when (v?.trim()?.lowercase()) {
    null, "", "unknown" -> "未知"
    "risk-on", "risk_on", "riskon" -> "风险偏好上升"
    "risk-off", "risk_off", "riskoff" -> "风险偏好下降"
    "neutral" -> "中性"
    else -> v ?: "未知"
}

fun displayErrorZh27(v: String?): String = when (v) {
    null -> "正常"
    "SocketTimeoutException" -> "请求超时"
    "UnknownHostException" -> "网络解析失败"
    "ConnectException" -> "连接失败"
    "SSLException" -> "安全连接失败"
    else -> "数据请求异常"
}
''', encoding='utf-8')

v6 = root / 'V6Activity.kt'
s = v6.read_text(encoding='utf-8')

# Full phrases only: do NOT translate protocol literals used in comparisons/parsing.
replacements = {
    'Intraday Preview（盘中预览）': '盘中主线预览',
    'Latest Official / Snapshot': '最新正式策略快照',
    'B4 Live Monitor（实时跟踪）': '综合确认池实时跟踪',
    'Data Status（数据状态）': '数据状态',
    'LIVE Preview': '实时预览',
    'Close Preview': '收盘预览',
    '盘中Preview': '盘中预览',
    'Mainline Preview': '主线预览',
    '暂无 Official Snapshot': '暂无正式策略快照',
    'Official Snapshot': '正式策略快照',
    'Time Machine（历史时间机器）': '历史时间机器',
    'Cohort Forward Tracking': '冻结批次后续收益跟踪',
    'Forward Tracking': '后续收益跟踪',
    'Pool Quotes': '股票池行情',
    'Live Monitor': '实时跟踪',
    'Daily Cohort': '每日冻结批次',
    'Momentum': '动量强度',
    'Breadth': '上涨扩散度',
    'Flow': '资金强度',
    'Score ': '评分 ',
    'Strategy Review（策略回顾）': '策略回顾',
}
for a, b in replacements.items():
    s = s.replace(a, b)

# Main header: raw backend status stays raw internally, translated only at display.
s = s.replace(
    'active?.let { "${it.date} · ${it.status} · ${it.regime}" }',
    'active?.let { "${it.date} · ${displayStatusZh27(it.status)} · ${displayRegimeZh27(it.regime)}" }'
)
# Common visible status values.
s = s.replace('Key("状态", s.status)', 'Key("状态", displayStatusZh27(s.status))')
s = s.replace('Key("状态", snap.status)', 'Key("状态", displayStatusZh27(snap.status))')
s = s.replace('Key("Regime", s.regime)', 'Key("市场状态", displayRegimeZh27(s.regime))')
s = s.replace('Key("Regime", snap.regime)', 'Key("市场状态", displayRegimeZh27(snap.regime))')
s = s.replace('Key("市场状态", s.regime)', 'Key("市场状态", displayRegimeZh27(s.regime))')
s = s.replace('Key("市场状态", snap.regime)', 'Key("市场状态", displayRegimeZh27(snap.regime))')
s = s.replace('s?.let { "${it.date} ${it.status}" }', 's?.let { "${it.date} ${displayStatusZh27(it.status)}" }')
s = s.replace('"${s.date} ${s.status}：', '"${s.date} ${displayStatusZh27(s.status)}：')
s = s.replace('Text(s.status.take(3)', 'Text(displayStatusZh27(s.status)')

# Mainline view keeps raw mode logic but displays Chinese options by converting the
# underlying values at the segmented button label.
s = s.replace('label = { Text(item, fontSize = 10.sp) }', 'label = { Text(displayChoiceZh27(item), fontSize = 10.sp) }')

# Preview state and factor labels.
s = s.replace('Text("${p.board.type} · ${p.state}"', 'Text("${p.board.type} · ${displayPreviewStateZh27(p.state)}"')
s = s.replace('Text(p.state, color = if (p.state == "Confirmed Candidate")', 'Text(displayPreviewStateZh27(p.state), color = if (p.state == "Confirmed Candidate")')
s = s.replace('ProgressLine("Momentum",', 'ProgressLine("动量强度",')
s = s.replace('ProgressLine("Breadth",', 'ProgressLine("上涨扩散度",')
s = s.replace('ProgressLine("Flow",', 'ProgressLine("资金强度",')

# Pool/history display keeps raw B0..B4 keys for data lookup, Chinese names on screen.
s = s.replace('Notice("$pool 名单来自 ${s.date} 的 ${s.status} 每日冻结批次；股票价格是 实时跟踪。名单本身不会盘中乱跳。")',
              'Notice("${displayPoolZh27(pool)}名单来自 ${s.date} 的 ${displayStatusZh27(s.status)}每日冻结批次；股票价格为实时跟踪，冻结名单不会盘中改写。")')
s = s.replace('Notice("$pool 名单来自 ${s.date} 的 ${s.status} Daily Cohort；股票价格是 Live Monitor。名单本身不会盘中乱跳。")',
              'Notice("${displayPoolZh27(pool)}名单来自 ${s.date} 的 ${displayStatusZh27(s.status)}每日冻结批次；股票价格为实时跟踪，冻结名单不会盘中改写。")')
s = s.replace('EmptyCard("该日 $pool 没有达标股票")', 'EmptyCard("该日${displayPoolZh27(pool)}没有达标股票")')
s = s.replace('EmptyCard("当日 $pool 为空")', 'EmptyCard("当日${displayPoolZh27(pool)}为空")')
s = s.replace('PerformanceCard("$pool 后续表现"', 'PerformanceCard("${displayPoolZh27(pool)}后续表现"')
s = s.replace('PerformanceCard("$pool 冻结批次后续收益跟踪"', 'PerformanceCard("${displayPoolZh27(pool)}后续收益跟踪"')
s = s.replace('PerformanceCard("$pool Cohort Forward Tracking"', 'PerformanceCard("${displayPoolZh27(pool)}后续收益跟踪"')

# Visible request errors should not leak Java exception class names.
s = s.replace('"请求异常：行情 ${quoteError ?: "OK"}；板块 ${boardError ?: "OK"}。页面会明确标记 stale，不再把旧值伪装成 Live。"',
              '"数据请求异常：行情${displayErrorZh27(quoteError)}；板块${displayErrorZh27(boardError)}。旧数据会明确标记为已过期，不会伪装成实时数据。"')

# Translate only the rendering of horizon labels; lookup remains 1D/5D/etc.
s = s.replace('Text(h, fontSize = 8.sp, color = Muted)', 'Text(displayHorizonZh27(h), fontSize = 8.sp, color = Muted)')

v6.write_text(s, encoding='utf-8')

# Additional helper used by Choice; keep data keys raw but screen labels Chinese.
with helper.open('a', encoding='utf-8') as f:
    f.write(r'''

fun displayChoiceZh27(v: String): String = when (v) {
    "盘中Preview", "盘中预览" -> "盘中预览"
    "Official" -> "正式主线"
    "B0", "B1", "B2", "B3", "B4", "B12", "B13", "B23", "TB0", "TB3", "TailCore",
    "EarlyWatch", "EarlyEntry", "Confirming", "EstablishedLowChase", "AvoidChase" -> displayPoolZh27(v)
    else -> v
}
''')

# Stock detail: pool codes are data keys; show descriptive Chinese names.
detail = root / 'DetailScreens.kt'
if detail.exists():
    ds = detail.read_text(encoding='utf-8')
    ds = ds.replace('pools.forEach { DetailTag(it, it == "B4") }', 'pools.forEach { DetailTag(displayPoolZh27(it), it == "B4") }')
    ds = ds.replace('Daily Cohort', '每日冻结批次')
    ds = ds.replace('Forward Tracking', '后续收益跟踪')
    ds = ds.replace('Official', '正式') if False else ds  # never mutate protocol literals globally
    detail.write_text(ds, encoding='utf-8')

# Files added by later versions: replace only known display phrases, not status keys.
for name in ('V25RadarTracking.kt', 'V26StockTrading.kt', 'TradeJournal.kt', 'ExecutionPanel.kt', 'PostCloseDashboard.kt', 'TradePlan.kt', 'TailDecision.kt'):
    p = root / name
    if not p.exists():
        continue
    text = p.read_text(encoding='utf-8')
    phrase_map = {
        'MFE': '最大有利涨幅',
        'MAE': '最大不利跌幅',
        '固定成员组合NAV': '固定成员组合净值',
        '今日NAV': '今日组合',
        '累计NAV': '累计组合',
        'Forward Tracking': '后续收益跟踪',
        'Trade Journal': '交易记录',
        'Mainline Preview': '主线预览',
        'Post-Close Facts（收盘事实层）': '收盘市场事实',
    }
    # Only replace phrases when they are embedded in a visible quoted string pattern;
    # MFE/MAE are intentionally skipped in JSON lookups by requiring nearby Chinese UI
    # forms handled in earlier v2.5 patch. Generic protocol keys remain unchanged.
    for a, b in phrase_map.items():
        if a in ('MFE', 'MAE'):
            text = text.replace(f'"{a} "', f'"{b} "')
            text = text.replace(f'"{a}：', f'"{b}：')
            text = text.replace(f'"{a}" ->', f'"{a}" ->')
        else:
            text = text.replace(a, b)
    p.write_text(text, encoding='utf-8')

# Final version bump.
g = Path('app/build.gradle.kts')
gs = g.read_text(encoding='utf-8')
gs = gs.replace('versionCode = 28', 'versionCode = 29')
gs = gs.replace('versionName = "2.6.0"', 'versionName = "2.7.0"')
if 'versionName = "2.7.0"' not in gs:
    raise SystemExit('v2.7 version bump failed')
g.write_text(gs, encoding='utf-8')

assert helper.exists()
assert 'displayPoolZh27' in detail.read_text(encoding='utf-8')
assert 'versionName = "2.7.0"' in g.read_text(encoding='utf-8')
print('v2.7 full-Chinese display layer integrated')