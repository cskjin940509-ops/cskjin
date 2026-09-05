package com.rui.astockstrategy.v6

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale

private fun text45(d: JSONObject?, key: String, fallback: String = "待同步"): String =
    if (d == null || d.isNull(key)) fallback else d.optString(key).ifBlank { fallback }
private fun number45(d: JSONObject?, key: String, suffix: String = ""): String =
    if (d == null || d.isNull(key)) "—" else d.optDouble(key).takeIf { it.isFinite() }
        ?.let { String.format(Locale.CHINA, "%.2f", it) + suffix } ?: "—"
private fun rows45(a: JSONArray?): List<JSONObject> =
    (0 until (a?.length() ?: 0)).mapNotNull { a?.optJSONObject(it) }
private fun strings45(a: JSONArray?): String =
    (0 until (a?.length() ?: 0)).joinToString("；") { a?.optString(it).orEmpty() }

@Composable
fun SelectionStatus45(data: JSONObject?) {
    val selection = data?.optJSONObject("selection45")
    val market = selection?.optJSONObject("market")
    val risk = selection?.optJSONObject("portfolioRisk")
    Card(shape = RoundedCornerShape(14.dp), colors = CardDefaults.cardColors(containerColor = Color(0xFFEAF0FF))) {
        Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Text("发现潜力 · 管理买卖 · 验证超额收益", fontWeight = FontWeight.Bold, fontSize = 15.sp)
            Text(if (selection == null) "客户端 v4.6 · 后台新规则待同步" else "云端规则：${text45(data, "strategyVersion")}", fontSize = 11.sp)
            Text(if (selection == null) "当前显示的是上次取得的组合；尚不能确认新版交易引擎已生效。" else
                "${if (risk?.optBoolean("allowNew") == true) "允许条件买入" else "暂停新增风险"} · ${text45(market, "reasonZh")}", fontSize = 11.sp)
            Text("掉出候选榜不会自动清仓。做T为模拟研究，尚未验证能稳定增加收益。", color = Color(0xFF606A7C), fontSize = 10.sp)
        }
    }
}

@Composable
fun SelectionStrategy45(data: JSONObject?) {
    val selection = data?.optJSONObject("selection45")
    val trading = data?.optJSONObject("tTrading")
    val risk = selection?.optJSONObject("portfolioRisk")
    val rules = data?.optJSONObject("rulesZh")
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        SelectionStatus45(data)
        StrategyResearch46(data, showAudits = false)
        Card(shape = RoundedCornerShape(14.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
            Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("交易规则与风险状态", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                Text("生效时间：${text45(selection, "activatedAt")}", fontSize = 11.sp)
                Text("当日单位净值收益：${number45(risk, "dailyUnitReturnPct", "%")}\n已确认日终回撤：${number45(risk, "confirmedCloseDrawdownPct", "%")}", fontSize = 12.sp)
                listOf("newEntry" to "买入", "lowPoint" to "买点", "position" to "仓位", "rebalance" to "执行", "exit" to "持有与退出", "stop" to "止损", "risk" to "组合风控").forEach { (key, title) ->
                    HorizontalDivider()
                    Text(title, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                    Text(if (selection == null) "等待新版云端规则同步" else text45(rules, key), fontSize = 11.sp)
                }
            }
        }
        Card(shape = RoundedCornerShape(14.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
            Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("底仓做T · 先卖后买", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                Text("每股每天最多1组；不超过昨日底仓20%、组合净值1%。强趋势保留底仓，风险退出优先。", fontSize = 12.sp)
                Text("已配对净收益：${number45(trading, "pairedNetPnl", "元")}\n未配对机会损益：${number45(trading, "unpairedOpportunityPnl", "元")}\n相对原股数持有增益：${number45(trading, "incrementalPnlVsUnchangedShares", "元")}", fontSize = 13.sp)
                Text(text45(trading, "noteZh", "尚无做T研究结果；没有成交不代表任务没有运行。"), fontSize = 10.sp, color = Color(0xFF606A7C))
                val cycles = rows45(trading?.optJSONArray("cycles"))
                if (cycles.isEmpty()) Text("暂无做T成交配对，等待满足条件。", fontSize = 11.sp)
                cycles.asReversed().take(30).forEach { x ->
                    HorizontalDivider()
                    val status = when (text45(x, "status")) { "PAIRED" -> "已配对"; "OPEN" -> "等待买回"; "UNPAIRED" -> "当日未买回"; "RISK_CANCELLED" -> "风险取消回补"; else -> text45(x, "status") }
                    Text("${text45(x, "name")} ${text45(x, "date")} · $status", fontWeight = FontWeight.Bold, fontSize = 12.sp)
                    Text("卖出${x.optInt("soldQty")}股 / 买回${x.optInt("boughtQty")}股\n配对净收益${number45(x, "realizedPairPnl", "元")} · 未配对损益${number45(x, "unpairedOpportunityPnl", "元")}", fontSize = 11.sp)
                }
                rows45(trading?.optJSONArray("signals")).take(20).forEach { x ->
                    Text("${text45(x, "name")}：${text45(x, "reasonZh")}", fontSize = 11.sp)
                }
            }
        }
        Card(shape = RoundedCornerShape(14.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
            Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("买点候选与未交易原因", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                val candidates = rows45(selection?.optJSONArray("candidates"))
                if (candidates.isEmpty()) Text("尚无当日完整买点数据。缺失数据不会自动放行。", fontSize = 11.sp)
                candidates.take(60).forEach { x ->
                    HorizontalDivider()
                    Text("${text45(x, "name")} ${text45(x, "code")} · ${text45(x, "sector")}", fontWeight = FontWeight.Bold, fontSize = 12.sp)
                    DecisionPlan46(x.optJSONObject("decisionPlan"))
                    Text(text45(x.optJSONObject("setup"), "reasonZh"), fontSize = 11.sp)
                    val rejects = strings45(x.optJSONArray("rejections"))
                    Text(if (rejects.isBlank()) "个股条件通过，仍需大盘、仓位和交易窗口许可" else "等待：$rejects", fontSize = 11.sp, color = Color(0xFF946000))
                }
            }
        }
        Card(shape = RoundedCornerShape(14.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
            Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("持仓风险线与待退出订单", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                rows45(data?.optJSONArray("positions")).forEach { x ->
                    DecisionPlan46(x.optJSONObject("decisionPlan"))
                    Text("${text45(x, "name")} · 保护线${number45(x, "hardStopPrice")} / 移动线${number45(x, "trailingStopPrice")}\n完整观察${x.optInt("completeObservedDays")}日 · 连续失效${x.optInt("invalidDayStreak")}日${if (x.optBoolean("atrFallback")) " · ATR缺失，保守保护" else ""}", fontSize = 11.sp)
                }
                val pending = rows45(selection?.optJSONArray("pendingExits"))
                if (pending.isEmpty()) Text("暂无待退出订单", fontSize = 11.sp)
                pending.forEach { x -> Text("${text45(x, "code")} · 剩余${x.optInt("remainingQty")}股\n${text45(x, "reasonZh")} · ${text45(x, "state")}", fontSize = 11.sp) }
                Text("阈值为待验证研究参数。软件只运行影子模拟，不连接券商。", color = Color(0xFF606A7C), fontSize = 10.sp)
            }
        }
    }
}
