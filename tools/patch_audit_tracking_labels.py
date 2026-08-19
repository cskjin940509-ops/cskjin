from pathlib import Path

p = Path('app/src/main/java/com/rui/astockstrategy/v6/V6Activity.kt')
s = p.read_text(encoding='utf-8')

s = s.replace(
'''fun snapshotAuditLabel(s: Snapshot): String = when (s.auditStatus) {
    "Verified" -> "已核对 / Verified"
    "LegacyUnverified" -> "旧版未验证"
    else -> "待核对"
}''',
'''fun snapshotAuditLabel(s: Snapshot): String = when (s.auditStatus) {
    "Verified" -> "已核对 / Verified"
    "PartiallyVerified" -> "部分核对 / 可跟踪"
    "LegacyUnverified" -> "未验证"
    else -> "待核对"
}'''
)

s = s.replace(
'''Text(if (s.auditStatus == "Verified") "已核对" else "未核对", fontSize = 8.sp, color = if (s.auditStatus == "Verified") Down else Amber)''',
'''Text(when (s.auditStatus) { "Verified" -> "已核对"; "PartiallyVerified" -> "部分核对"; else -> "未核对" }, fontSize = 8.sp, color = if (s.auditStatus == "Verified") Down else Amber)'''
)

s = s.replace(
'''Text("该批次保留原冻结名单用于审计，但在完成时点、因子来源和双源价格核对前，不纳入胜率、Alpha或池间比较。", fontSize = 10.sp, color = Ink)''',
'''Text(if (s.auditStatus == "PartiallyVerified") "该批次已完成可恢复数据核查，可展示经入场价验证的参考 Tracking；因缺少原始 point-in-time 成分等证据，暂不纳入胜率、Alpha或因子成绩统计。" else "该批次保留原冻结名单用于审计；证据不足时不纳入胜率、Alpha或池间比较。", fontSize = 10.sp, color = Ink)'''
)

p.write_text(s, encoding='utf-8')
