package com.rui.astockstrategy.v6

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import kotlinx.coroutines.delay
import kotlin.math.abs

private val Trade26Red = Color(0xFFD54432)
private val Trade26Green = Color(0xFF16855B)
private val Trade26Blue = Color(0xFF3567B7)
private val Trade26Muted = Color(0xFF6D7480)
private val Trade26Bg = Color(0xFFF7F8FC)

@Composable
fun StockTradingPanel26(
    code: String,
    name: String,
    fallbackPrice: Double?,
    sourceDate: String?,
    poolLabels: List<String>,
    signal: String?,
) {
    val context = LocalContext.current
    var ledgerVersion by remember(code) { mutableIntStateOf(0) }
    var mode by remember(code) { mutableStateOf("REAL") }
    var side by remember(code) { mutableStateOf<String?>(null) }
    var live by remember(code) { mutableStateOf<Quote?>(null) }
    var message by remember(code) { mutableStateOf<String?>(null) }

    LaunchedEffect(code) {
        while (true) {
            runCatching { DataApi.fetchQuotes(listOf(symbol(code)))[symbol(code)] }
                .onSuccess { if (it != null) live = it }
            delay(5_000)
        }
    }

    val price = live?.price ?: fallbackPrice
    val position = remember(code, mode, ledgerVersion) { TradeLedger.position(context, code, mode) }
    val realized = remember(code, mode, ledgerVersion) {
        TradeLedger.records(context)
            .filter { it.code == code && it.mode == mode && it.side == "SELL" }
            .mapNotNull { it.realizedPnl }
            .sum()
    }
    val unrealized = if (position != null && price != null) price * position.qty - position.costBasis else null
    val unrealizedPct = if (unrealized != null && position != null && position.costBasis > 0) unrealized / position.costBasis * 100.0 else null
    val marketValue = if (position != null && price != null) price * position.qty else null
    val totalPnl = (unrealized ?: 0.0) + realized

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(containerColor = Color.White)
    ) {
        Column(Modifier.fillMaxWidth().padding(13.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("交易与持仓", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                    Text("从筛选结果直接记录成交，无需重复填写股票代码和名称", color = Trade26Muted, fontSize = 9.sp)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(price?.let { String.format("%.2f", it) } ?: "—", fontWeight = FontWeight.Bold, fontSize = 18.sp)
                    Text(live?.change?.let { String.format("%+.2f%%", it) } ?: "实时价待同步", color = live?.change?.let { if (it >= 0) Trade26Red else Trade26Green } ?: Trade26Muted, fontSize = 9.sp)
                }
            }

            Row(horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                FilterChip(selected = mode == "REAL", onClick = { mode = "REAL" }, label = { Text("实盘记录", fontSize = 9.sp) })
                FilterChip(selected = mode == "PAPER", onClick = { mode = "PAPER" }, label = { Text("模拟交易", fontSize = 9.sp) })
            }

            if (position == null) {
                Surface(color = Trade26Bg, shape = RoundedCornerShape(12.dp)) {
                    Text("当前没有${if (mode == "REAL") "实盘" else "模拟"}持仓", Modifier.fillMaxWidth().padding(10.dp), color = Trade26Muted, fontSize = 10.sp)
                }
            } else {
                Surface(color = Trade26Bg, shape = RoundedCornerShape(12.dp)) {
                    Column(Modifier.fillMaxWidth().padding(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Row(Modifier.fillMaxWidth()) {
                            TradeMetric26("持仓数量", "${position.qty}股", Modifier.weight(1f))
                            TradeMetric26("平均成本", String.format("%.3f", position.avgCost), Modifier.weight(1f))
                            TradeMetric26("当前市值", marketValue?.let(::money26) ?: "—", Modifier.weight(1f))
                        }
                        HorizontalDivider(color = Color(0xFFE9EAF0))
                        Row(Modifier.fillMaxWidth()) {
                            TradeMetric26("持仓收益", unrealized?.let(::moneySigned26) ?: "—", Modifier.weight(1f), pnlColor26(unrealized))
                            TradeMetric26("收益率", unrealizedPct?.let { String.format("%+.2f%%", it) } ?: "—", Modifier.weight(1f), pnlColor26(unrealized))
                            TradeMetric26("今日可卖", "${position.sellableQty}股", Modifier.weight(1f))
                        }
                        Row(Modifier.fillMaxWidth()) {
                            TradeMetric26("已实现盈亏", moneySigned26(realized), Modifier.weight(1f), pnlColor26(realized))
                            TradeMetric26("累计盈亏", moneySigned26(totalPnl), Modifier.weight(1f), pnlColor26(totalPnl))
                            TradeMetric26("首次买入", position.firstBuyDate?.takeLast(5) ?: "—", Modifier.weight(1f))
                        }
                    }
                }
            }

            if (poolLabels.isNotEmpty()) {
                Text("来源：${poolLabels.joinToString(" / ") { poolZh26(it) }}${sourceDate?.let { " · $it" } ?: ""}", color = Trade26Muted, fontSize = 8.sp)
            }
            message?.let { Text(it, color = Trade26Blue, fontSize = 9.sp) }

            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(9.dp)) {
                Button(
                    onClick = { side = "BUY" },
                    enabled = price != null && price > 0,
                    modifier = Modifier.weight(1f).height(44.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Trade26Red)
                ) { Text(if (position == null) "买入" else "加仓", fontWeight = FontWeight.Bold) }
                Button(
                    onClick = { side = "SELL" },
                    enabled = position != null && position.sellableQty > 0 && price != null && price > 0,
                    modifier = Modifier.weight(1f).height(44.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Trade26Green)
                ) { Text("卖出", fontWeight = FontWeight.Bold) }
            }
            Text(
                if (position != null && position.sellableQty <= 0) "当日新买部分按普通A股交易约束暂不可卖。" else "这里记录你的实际/模拟成交，不会向券商发送订单。",
                color = Trade26Muted,
                fontSize = 8.sp
            )
        }
    }

    side?.let { selectedSide ->
        StockTradeDialog26(
            code = code,
            name = name,
            side = selectedSide,
            mode = mode,
            livePrice = price,
            maxSellQty = if (selectedSide == "SELL") position?.sellableQty else null,
            sourceDate = sourceDate,
            signal = signal,
            onDismiss = { side = null },
            onSaved = {
                side = null
                ledgerVersion++
                message = if (selectedSide == "BUY") "买入成交已记录，持仓收益已更新" else "卖出成交已记录，已实现收益已更新"
            }
        )
    }
}

@Composable
private fun StockTradeDialog26(
    code: String,
    name: String,
    side: String,
    mode: String,
    livePrice: Double?,
    maxSellQty: Int?,
    sourceDate: String?,
    signal: String?,
    onDismiss: () -> Unit,
    onSaved: () -> Unit,
) {
    val context = LocalContext.current
    val isBuy = side == "BUY"
    var priceText by remember(side, livePrice) { mutableStateOf(livePrice?.let { String.format("%.3f", it) } ?: "") }
    var qtyText by remember(side, maxSellQty) {
        mutableStateOf(if (isBuy) "100" else (maxSellQty?.coerceAtMost(100)?.coerceAtLeast(1)?.toString() ?: ""))
    }
    var feeText by remember(side) { mutableStateOf("0") }
    var note by remember(side) { mutableStateOf("") }
    var error by remember(side) { mutableStateOf<String?>(null) }
    val p = priceText.toDoubleOrNull()
    val q = qtyText.toIntOrNull()
    val amount = if (p != null && q != null && p > 0 && q > 0) p * q else null

    Dialog(onDismissRequest = onDismiss) {
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(20.dp),
            colors = CardDefaults.cardColors(containerColor = Color.White)
        ) {
            Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(if (isBuy) "买入 $name" else "卖出 $name", fontWeight = FontWeight.Bold, fontSize = 18.sp, color = if (isBuy) Trade26Red else Trade26Green)
                        Text("$code · ${if (mode == "REAL") "实盘记录" else "模拟交易"}", color = Trade26Muted, fontSize = 9.sp)
                    }
                    Text(livePrice?.let { "现价 ${String.format("%.2f", it)}" } ?: "现价待同步", fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
                }

                OutlinedTextField(
                    value = priceText,
                    onValueChange = { priceText = it.filter { ch -> ch.isDigit() || ch == '.' }.take(12) },
                    label = { Text("实际成交价") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    trailingIcon = {
                        if (livePrice != null) TextButton(onClick = { priceText = String.format("%.3f", livePrice) }) { Text("用现价", fontSize = 9.sp) }
                    }
                )

                OutlinedTextField(
                    value = qtyText,
                    onValueChange = { qtyText = it.filter(Char::isDigit).take(9) },
                    label = { Text(if (isBuy) "买入数量（股）" else "卖出数量（股）") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )

                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    if (isBuy) {
                        listOf(100, 300, 500, 1000).forEach { n ->
                            AssistChip(onClick = { qtyText = n.toString() }, label = { Text("${n}股", fontSize = 8.sp) }, modifier = Modifier.weight(1f))
                        }
                    } else {
                        val mx = maxSellQty ?: 0
                        listOf(
                            "100股" to mx.coerceAtMost(100),
                            "半仓" to (mx / 2).coerceAtLeast(if (mx > 0) 1 else 0),
                            "全部" to mx,
                        ).forEach { (label, n) ->
                            AssistChip(onClick = { if (n > 0) qtyText = n.toString() }, enabled = n > 0, label = { Text(label, fontSize = 8.sp) }, modifier = Modifier.weight(1f))
                        }
                    }
                }

                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = {
                        val cur = qtyText.toIntOrNull() ?: 0
                        qtyText = (cur - 100).coerceAtLeast(if (isBuy) 100 else 1).toString()
                    }, modifier = Modifier.weight(1f)) { Text("－100股") }
                    OutlinedButton(onClick = {
                        val cur = qtyText.toIntOrNull() ?: 0
                        val next = cur + 100
                        qtyText = if (!isBuy && maxSellQty != null) next.coerceAtMost(maxSellQty).toString() else next.toString()
                    }, modifier = Modifier.weight(1f)) { Text("＋100股") }
                }

                Surface(color = Trade26Bg, shape = RoundedCornerShape(12.dp)) {
                    Column(Modifier.fillMaxWidth().padding(10.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                        TradeRow26("预计成交额", amount?.let(::money26) ?: "—")
                        if (!isBuy) TradeRow26("今日最多可卖", maxSellQty?.let { "${it}股" } ?: "—")
                        TradeRow26("成交方式", "按你输入的实际成交价记账")
                    }
                }

                OutlinedTextField(
                    value = feeText,
                    onValueChange = { feeText = it.filter { ch -> ch.isDigit() || ch == '.' }.take(12) },
                    label = { Text("实际手续费/税费") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                OutlinedTextField(value = note, onValueChange = { note = it.take(120) }, label = { Text("备注（可选）") }, minLines = 2, modifier = Modifier.fillMaxWidth())

                Text("确认后只写入本机交易账本，不会向券商提交订单。", color = Trade26Muted, fontSize = 8.sp)
                error?.let { Text(it, color = Trade26Green, fontSize = 9.sp) }

                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = onDismiss, modifier = Modifier.weight(1f)) { Text("取消") }
                    Button(
                        onClick = {
                            val price = priceText.toDoubleOrNull()
                            val qty = qtyText.toIntOrNull()
                            val fee = feeText.toDoubleOrNull() ?: 0.0
                            if (price == null || price <= 0) { error = "请填写有效成交价"; return@Button }
                            if (qty == null || qty <= 0) { error = "请填写有效成交数量"; return@Button }
                            if (!isBuy && maxSellQty != null && qty > maxSellQty) { error = "卖出数量超过今日可卖数量"; return@Button }
                            runCatching {
                                TradeLedger.add(
                                    context = context,
                                    code = code,
                                    name = name,
                                    side = side,
                                    mode = mode,
                                    price = price,
                                    qty = qty,
                                    fee = fee,
                                    source = "个股详情",
                                    sourceDate = sourceDate,
                                    signal = signal?.take(60),
                                    note = note.takeIf { it.isNotBlank() },
                                )
                            }.onSuccess { onSaved() }.onFailure { error = it.message ?: "保存失败" }
                        },
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.buttonColors(containerColor = if (isBuy) Trade26Red else Trade26Green)
                    ) { Text(if (isBuy) "确认记录买入" else "确认记录卖出", fontWeight = FontWeight.Bold) }
                }
            }
        }
    }
}

@Composable
private fun TradeMetric26(label: String, value: String, modifier: Modifier, color: Color = Trade26Muted) {
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally) {
        Text(label, fontSize = 8.sp, color = Trade26Muted)
        Text(value, fontSize = 10.sp, fontWeight = FontWeight.SemiBold, color = color)
    }
}

@Composable
private fun TradeRow26(label: String, value: String) {
    Row(Modifier.fillMaxWidth()) {
        Text(label, Modifier.weight(1f), fontSize = 9.sp, color = Trade26Muted)
        Text(value, fontSize = 9.sp, fontWeight = FontWeight.SemiBold)
    }
}

fun poolZh26(v: String): String = when (v) {
    "B0" -> "基础强度池（B0）"
    "B1" -> "两融确认池（B1）"
    "B2" -> "指数基金确认池（B2）"
    "B3" -> "主力资金确认池（B3）"
    "B4" -> "综合确认池（B4）"
    "B12" -> "两融+指数基金联合池"
    "B13" -> "两融+主力联合池"
    "B23" -> "指数基金+主力联合池"
    "EarlyWatch" -> "提前观察池"
    "EarlyEntry" -> "提前介入候选池"
    "Confirming" -> "确认中候选池"
    "EstablishedLowChase" -> "已成主线低追高风险池"
    else -> v
}

private fun pnlColor26(v: Double?): Color = if ((v ?: 0.0) >= 0) Trade26Red else Trade26Green
private fun money26(v: Double): String = when {
    abs(v) >= 1e8 -> String.format("%.2f亿", v / 1e8)
    abs(v) >= 1e4 -> String.format("%.2f万", v / 1e4)
    else -> String.format("%.2f", v)
}
private fun moneySigned26(v: Double) = (if (v >= 0) "+" else "") + money26(v)
