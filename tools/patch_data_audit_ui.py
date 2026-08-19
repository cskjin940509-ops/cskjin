from pathlib import Path

p=Path('app/src/main/java/com/rui/astockstrategy/v6/V6Activity.kt')
s=p.read_text(encoding='utf-8')

# Extend frozen snapshot model with explicit auditability.
old='''    val strategyVersion: String?,\n    val mainlines: List<String>,'''
new='''    val strategyVersion: String?,\n    val auditStatus: String?,\n    val performanceEligible: Boolean,\n    val auditIssues: List<String>,\n    val mainlines: List<String>,'''
if old in s and 'val auditStatus: String?' not in s:
    s=s.replace(old,new,1)

# Parse audit metadata before constructing Snapshot.
needle='''        return Snapshot(\n            date = date,'''
insert='''        val audit = o.optJSONObject("audit")\n        val auditStatus = audit?.optString("status")?.takeIf { it.isNotBlank() }\n        val performanceEligible = audit?.optBoolean("eligibleForPerformanceComparison", auditStatus != "LegacyUnverified") ?: false\n        val auditIssues = arrStrings(audit?.optJSONArray("issues"))\n        return Snapshot(\n            date = date,'''
if needle in s and 'val audit = o.optJSONObject("audit")' not in s:
    s=s.replace(needle,insert,1)

old='''            strategyVersion = o.optString("strategyVersion").takeIf { it.isNotBlank() },\n            mainlines = arrStrings(o.optJSONArray("mainlines")),'''
new='''            strategyVersion = o.optString("strategyVersion").takeIf { it.isNotBlank() },\n            auditStatus = auditStatus,\n            performanceEligible = performanceEligible,\n            auditIssues = auditIssues,\n            mainlines = arrStrings(o.optJSONArray("mainlines")),'''
if old in s:
    s=s.replace(old,new,1)

# Root title must never equate legacy Official with verified data.
s=s.replace(
    'active?.let { "${it.date} · ${it.status} · ${it.regime}" } ?: "等待策略快照",',
    'active?.let { "${it.date} · ${snapshotAuditLabel(it)} · ${it.regime}" } ?: "等待策略快照",'
)
s=s.replace(
    'color = if (active?.status == "Official") Down else Amber',
    'color = if (active?.auditStatus == "Verified") Down else Amber'
)

# Current status cards.
s=s.replace('Key("状态", s.status)', 'Key("状态", snapshotAuditLabel(s))')
s=s.replace('Key("正式策略", s?.let { "${it.date} ${it.status}" } ?: "未同步")', 'Key("正式策略", s?.let { "${it.date} ${snapshotAuditLabel(it)}" } ?: "未同步")')
s=s.replace('Key("日期", snap.date); Key("状态", snap.status);', 'Key("日期", snap.date); Key("状态", snapshotAuditLabel(snap));')

# Add warnings on the main screens where trust matters.
old='''            val b4 = s.pools["B4"].orEmpty()'''
new='''            if (!s.performanceEligible) {\n                item { AuditWarning(s) }\n            }\n            val b4 = s.pools["B4"].orEmpty()'''
if old in s and 'item { AuditWarning(s) }' not in s:
    s=s.replace(old,new,1)

s=s.replace(
    'item { Notice("${s.date} ${s.status}：这一页只显示当日冻结结果，不会随今天行情改写。") }',
    'item { Notice("${s.date} ${snapshotAuditLabel(s)}：这一页只显示当日冻结结果，不会随今天行情改写。") }; if (!s.performanceEligible) item { AuditWarning(s) }'
)

# Pairwise patch has already transformed this string by build time.
s=s.replace(
    'Notice("${poolTitle(pool)} 来自 ${s.date} 的 ${zhStatus(s.status)}每日批次；名单本身冻结，价格独立更新。组合池要求对应两个资金因子都正式达标。")',
    'Notice("${poolTitle(pool)} 来自 ${s.date} 的 ${snapshotAuditLabel(s)}；名单本身冻结，价格独立更新。组合池要求对应两个资金因子都正式达标。")'
)

# Hide model-performance cards for cohorts that have not passed audit.
s=s.replace(
    'item { PerformanceCard("${poolTitle(pool)} 后续表现", s.poolPerformance[pool]) }',
    'if (s.performanceEligible) item { PerformanceCard("${poolTitle(pool)} 后续表现", s.poolPerformance[pool]) } else item { AuditPerformanceBlocked() }'
)
s=s.replace(
    'item { PerformanceCard("${poolTitle(pool)} 后续跟踪", snap.poolPerformance[pool]) }',
    'if (snap.performanceEligible) item { PerformanceCard("${poolTitle(pool)} 后续跟踪", snap.poolPerformance[pool]) } else item { AuditPerformanceBlocked() }'
)

# History page: warning and no misleading per-stock tracking strip.
old='''        item { PoolSelector(pool) { pool = it } }\n        val codes = snap.pools[pool].orEmpty()'''
new='''        if (!snap.performanceEligible) item { AuditWarning(snap) }\n        item { PoolSelector(pool) { pool = it } }\n        val codes = snap.pools[pool].orEmpty()'''
if old in s:
    s=s.replace(old,new,1)

s=s.replace(
    'Spacer(Modifier.height(6.dp))\n            TrackingStrip(perf)',
    'Spacer(Modifier.height(6.dp))\n            if (s.performanceEligible) TrackingStrip(perf) else Text("旧版未验证 · 收益仅留档，不计入策略统计", fontSize = 9.sp, color = Amber)'
)

# History chip trust cue.
s=s.replace(
    'colors = CardDefaults.cardColors(containerColor = if (selected) SoftBlue else if (s.status == "Official") SoftGreen else Color.White),',
    'colors = CardDefaults.cardColors(containerColor = if (selected) SoftBlue else if (s.auditStatus == "Verified") SoftGreen else Color(0xFFFFF1E7)),'
)
s=s.replace(
    'Text(s.status.take(3), fontSize = 8.sp, color = if (s.status == "Official") Down else Amber)',
    'Text(if (s.auditStatus == "Verified") "已核对" else "未核对", fontSize = 8.sp, color = if (s.auditStatus == "Verified") Down else Amber)'
)

# Audit helpers inserted before PerformanceCard.
marker='''@Composable\nfun PerformanceCard(title: String, p: JSONObject?) {'''
helpers='''fun snapshotAuditLabel(s: Snapshot): String = when (s.auditStatus) {\n    "Verified" -> "已核对 / Verified"\n    "LegacyUnverified" -> "旧版未验证"\n    else -> "待核对"\n}\n\n@Composable\nfun AuditWarning(s: Snapshot) {\n    Surface(color = Color(0xFFFFF1E7), shape = RoundedCornerShape(14.dp)) {\n        Column(Modifier.fillMaxWidth().padding(11.dp)) {\n            Text("⚠ ${snapshotAuditLabel(s)}", fontWeight = FontWeight.Bold, color = Amber)\n            Text("该批次保留原冻结名单用于审计，但在完成时点、因子来源和双源价格核对前，不纳入胜率、Alpha或池间比较。", fontSize = 10.sp, color = Ink)\n            if (s.auditIssues.isNotEmpty()) Text(s.auditIssues.joinToString(" · "), fontSize = 8.sp, color = Muted, maxLines = 3)\n        }\n    }\n}\n\n@Composable\nfun AuditPerformanceBlocked() {\n    Notice("该批次尚未通过数据审计，历史收益只保留原始记录，不进入模型表现统计。")\n}\n\n'''
if marker in s and 'fun snapshotAuditLabel(' not in s:
    s=s.replace(marker,helpers+marker,1)

p.write_text(s,encoding='utf-8')

# v1.4 after Yunai v1.3 patch.
g=Path('app/build.gradle.kts')
gs=g.read_text(encoding='utf-8')
gs=gs.replace('versionCode = 14','versionCode = 15')
gs=gs.replace('versionName = "1.3.0"','versionName = "1.4.0"')
g.write_text(gs,encoding='utf-8')
