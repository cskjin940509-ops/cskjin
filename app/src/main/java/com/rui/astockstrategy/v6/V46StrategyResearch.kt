package com.rui.astockstrategy.v6

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale

private fun rows46(a: JSONArray?): List<JSONObject> =
    (0 until (a?.length() ?: 0)).mapNotNull { a?.optJSONObject(it) }
private fun text46(o: JSONObject?, key: String, fallback: String = "待同步"): String =
    if (o == null || o.isNull(key)) fallback else o.optString(key).ifBlank { fallback }
private fun number46(o: JSONObject?, key: String, unit: String = ""): String =
    if (o == null || o.isNull(key)) "—" else o.optDouble(key).takeIf { it.isFinite() }
        ?.let { String.format(Locale.CHINA, "%.2f", it) + unit } ?: "—"

@Composable
private fun ResearchCard46(title: String, content: @Composable ColumnScope.() -> Unit) {
    Card(shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, fontSize = 17.sp, fontWeight = FontWeight.Bold)
            content()
        }
    }
}

@Composable
fun StrategyResearch46(data: JSONObject?, showAudits: Boolean = true) {
    val report = data?.optJSONObject("strategyResearch")
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        ResearchCard46("策略目标与当前优先级") {
            Text("提前发现潜力 → 优化买卖 → 按需做T", fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
            Text("比较扣费后的超额收益与回撤。相对低位布局、趋势转弱退出；不把事后最低和最高点当作可预测买卖点。", fontSize = 13.sp)
            if (report == null) {
                Text("新版验证报告尚未同步，无法判断任何审核已通过。", color = Color(0xFF946000), fontSize = 13.sp)
            } else {
                Text(text46(report, "currentPriorityZh"), fontSize = 13.sp)
                Text("报告时间：${text46(report, "updatedAt")}\n${text46(report, "productionStatusZh")}", fontSize = 12.sp, color = Color(0xFF626B7A))
            }
        }
        rows46(report?.optJSONArray("stages")).forEach { stage ->
            ResearchCard46(text46(stage, "titleZh")) {
                Text(text46(stage, "statusZh"), color = Color(0xFF3155D6), fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                if (stage.has("matureSignalDates")) {
                    val total = if (stage.has("requiredSignalDates")) " / ${stage.optInt("requiredSignalDates")}日复核门槛" else ""
                    Text("已观测：${stage.optInt("matureSignalDates")}个日期$total", fontSize = 13.sp)
                }
                if (stage.has("meanObservedExcessVsB0Pp")) {
                    Text("10日原始价格观察超额：${number46(stage, "meanObservedExcessVsB0Pp", "个百分点")}", fontSize = 13.sp)
                    Text("对比当时B0基线；未扣可成交成本、未校正除权分红，不能当作策略收益。", fontSize = 12.sp, color = Color(0xFF626B7A))
                }
                Text(text46(stage, "reasonZh"), fontSize = 13.sp)
                Text("下一步：${text46(stage, "nextActionZh")}", fontSize = 13.sp)
            }
        }
        val timing = report?.optJSONObject("timingComparison")
        if (timing != null) ResearchCard46("买卖管理与简单持有对照") {
            Text("两组均关闭做T · 确认收盘${timing.optInt("closeSampleDays")}日", fontSize = 13.sp)
            Text("买卖管理收益：${number46(timing, "managedReturnPct", "%")}\n简单持有收益：${number46(timing, "simpleReturnPct", "%")}\n管理增益：${number46(timing, "incrementalReturnPp", "个百分点")}", fontSize = 14.sp)
            Text(text46(timing, "noteZh"), fontSize = 12.sp, color = Color(0xFF626B7A))
        }
        val control = report?.optJSONObject("tComparison")
        if (control != null) ResearchCard46("做T与独立无T组合对照") {
            Text(text46(control, "statusZh"), fontSize = 14.sp)
            Text("共同起点：${text46(control, "startedAt")}\n确认收盘：${text46(control, "asOfDate")} · ${control.optInt("closeSampleDays")}日", fontSize = 12.sp)
            Text("含T总收益：${number46(control, "withTReturnPct", "%")}\n无T总收益：${number46(control, "withoutTReturnPct", "%")}\n做T增益：${number46(control, "incrementalReturnPp", "个百分点")}", fontSize = 14.sp)
            Text("含T回撤：${number46(control, "withTDrawdownPct", "%")}\n无T回撤：${number46(control, "withoutTDrawdownPct", "%")}", fontSize = 13.sp)
            Text(text46(control, "noteZh", "等待完整同起点对照结果；空值不视为零收益。"), fontSize = 12.sp, color = Color(0xFF626B7A))
        }
        if (showAudits) ResearchCard46("真实审核进度") {
            val audits = rows46(report?.optJSONArray("audits"))
            if (audits.isEmpty()) Text("未收到审核证据，所有项目状态未知。", fontSize = 13.sp)
            audits.forEach { audit ->
                HorizontalDivider()
                val status = when (audit.optString("status")) {
                    "CHECKED" -> "✓ 本项证据已核对"
                    "PARTIAL" -> "部分完成"
                    "MISSING" -> "缺少证据"
                    "PENDING_REVIEW" -> "待验证与复核"
                    else -> "状态未知"
                }
                Text("${text46(audit, "titleZh")} · $status", fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                Text("${audit.optInt("completed")} / ${audit.optInt("total")} · ${text46(audit, "checkedAt")}", fontSize = 12.sp)
                Text(text46(audit, "reasonZh"), fontSize = 13.sp)
                Text("证据：${text46(audit, "evidencePath")}", fontSize = 11.sp, color = Color(0xFF626B7A))
            }
        }
    }
}

@Composable
fun DecisionPlan46(plan: JSONObject?) {
    if (plan == null) {
        Text("新版决策说明待同步", fontSize = 12.sp, color = Color(0xFF946000))
        return
    }
    Text(text46(plan, "actionZh"), fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
    if (plan.has("buyZoneLow")) {
        Text("观察买入区间：${number46(plan, "buyZoneLow")}–${number46(plan, "buyZoneHigh")}\n初始保护线：${number46(plan, "initialProtectionPrice")}\n历史阻力参考：${number46(plan, "resistanceReference")}", fontSize = 13.sp)
        Text(text46(plan, "forecastZh"), fontSize = 12.sp)
    } else {
        Text(text46(plan, "reasonZh"), fontSize = 13.sp)
        Text(text46(plan, "takeProfitZh"), fontSize = 13.sp)
        Text(text46(plan, "tPolicyZh"), fontSize = 12.sp)
    }
}
