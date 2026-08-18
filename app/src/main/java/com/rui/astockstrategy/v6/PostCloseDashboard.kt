package com.rui.astockstrategy.v6

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun PostCloseDashboard(
    quotes: Map<String, Quote>,
    preview: List<PreviewSector>,
    official: Snapshot?
) {
    val indices = listOf(
        "sh000001" to "上证",
        "sz399006" to "创业板",
        "sh000688" to "科创50",
        "sh000300" to "沪深300",
        "sh000852" to "中证1000"
    )
    val available = indices.mapNotNull { (sym, label) -> quotes[sym]?.let { label to it } }
    val totalAmount = available.mapNotNull { it.second.amount }.sum()

    Text("Post-close Market Snapshot（收盘市场截面）", fontWeight = FontWeight.Bold, fontSize = 17.sp)
    Card(
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
    ) {
        Column(Modifier.fillMaxWidth().padding(13.dp)) {
            Text("15:00 后先展示真实收盘行情，不等待策略批次。", fontSize = 11.sp)
            Spacer(Modifier.height(8.dp))
            available.chunked(2).forEach { pair ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    pair.forEach { (label, q) ->
                        Column(Modifier.weight(1f)) {
                            Text(label, fontSize = 10.sp)
                            Text(q.price?.let { String.format("%.2f", it) } ?: "—", fontWeight = FontWeight.Bold)
                            Text(q.change?.let { String.format("%+.2f%%", it) } ?: "—", fontSize = 11.sp)
                            Text(q.quoteTime ?: "", fontSize = 9.sp)
                        }
                    }
                    if (pair.size == 1) Spacer(Modifier.weight(1f))
                }
                Spacer(Modifier.height(7.dp))
            }
            if (totalAmount > 0.0) {
                Text("主要指数成交额口径合计 ${formatCnMoney(totalAmount)}", fontSize = 10.sp)
            }
            Text(
                if (official == null) "Official Daily Cohort：策略计算中" else "Official Daily Cohort：${official.date} ${official.status}",
                fontSize = 11.sp,
                fontWeight = FontWeight.SemiBold
            )
        }
    }

    Spacer(Modifier.height(4.dp))
    Text("收盘主线候选 · 基于当天板块收盘截面", fontWeight = FontWeight.Bold, fontSize = 15.sp)
    if (preview.isEmpty()) {
        Card(shape = RoundedCornerShape(14.dp)) {
            Text("板块收盘数据暂未取得；策略层不会用旧数据冒充当天结果。", Modifier.padding(12.dp), fontSize = 11.sp)
        }
    } else {
        preview.take(8).forEach { p ->
            Card(Modifier.fillMaxWidth(), shape = RoundedCornerShape(14.dp)) {
                Row(Modifier.fillMaxWidth().padding(11.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                    Column(Modifier.weight(1f)) {
                        Text(p.board.name, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                        Text("${p.state} · Breadth ${String.format("%.0f%%", p.breadth)}", fontSize = 10.sp)
                    }
                    Spacer(Modifier.width(8.dp))
                    Column {
                        Text(p.board.change?.let { String.format("%+.2f%%", it) } ?: "—", fontWeight = FontWeight.Bold)
                        Text("Score ${String.format("%.0f", p.score)}", fontSize = 9.sp)
                    }
                }
            }
            Spacer(Modifier.height(6.dp))
        }
    }
}

private fun formatCnMoney(v: Double): String = when {
    v >= 1e12 -> String.format("%.2f万亿", v / 1e12)
    v >= 1e8 -> String.format("%.2f亿", v / 1e8)
    v >= 1e4 -> String.format("%.2f万", v / 1e4)
    else -> String.format("%.0f", v)
}
