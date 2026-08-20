from pathlib import Path

root = Path('app/src/main/java/com/rui/astockstrategy/v6')

trade = root / 'V26StockTrading.kt'
trade.write_text(r'''package com.rui.astockstrategy.v6

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
''', encoding='utf-8')

detail = root / 'DetailScreens.kt'
ds = detail.read_text(encoding='utf-8')
anchor = '''        val reason = f?.reason ?: meta?.reason\n'''
if 'StockTradingPanel26(' not in ds:
    block = '''        item {\n            StockTradingPanel26(\n                code = code,\n                name = name,\n                fallbackPrice = current,\n                sourceDate = date,\n                poolLabels = pools,\n                signal = f?.reason ?: meta?.reason\n            )\n        }\n'''
    if anchor not in ds:
        raise SystemExit('stock detail trading insertion point not found')
    ds = ds.replace(anchor, block + anchor, 1)

ds = ds.replace('Daily Cohort', '每日冻结批次')
ds = ds.replace('· 点开详情', '· 点开查看并交易')
detail.write_text(ds, encoding='utf-8')

radar = root / 'V25RadarTracking.kt'
if radar.exists():
    rs = radar.read_text(encoding='utf-8')
    if 'import androidx.compose.foundation.clickable' not in rs:
        rs = rs.replace('import androidx.compose.foundation.background\n', 'import androidx.compose.foundation.background\nimport androidx.compose.foundation.clickable\n', 1)
    rs = rs.replace('从开盘滚动识别 Emerging → Confirming，不等涨完才筛', '从开盘滚动识别潜在形成 → 确认中，不等涨完才筛')
    rs = rs.replace('Text("提前候选",', 'Text("提前介入候选",')
    rs = rs.replace('Text("形成分是未校准的研究评分，不是上涨概率；高追高风险时即使主线强也不建议机械追价。"', 'Text("形成分是未校准的研究评分，不代表上涨概率；追高风险高时即使主线强也不建议机械追价。"')
    rs = rs.replace('Mini25("MFE",', 'Mini25("最大有利涨幅",')
    rs = rs.replace('Mini25("MAE",', 'Mini25("最大不利跌幅",')
    rs = rs.replace('Text("固定成员组合NAV",', 'Text("固定成员组合净值",')
    rs = rs.replace('Mini25("今日NAV",', 'Mini25("今日组合",')
    rs = rs.replace('Mini25("累计NAV",', 'Mini25("累计组合",')
    rs = rs.replace('Text("累计NAV是组合绩效；平均个股累计仅作诊断，成员退出当前池也不会从历史记录删除。"', 'Text("累计组合收益才是组合绩效；平均个股累计仅作诊断，成员退出当前池也不会从历史记录删除。"')
    old = 'Row(Modifier.fillMaxWidth()) {\n                            Column(Modifier.weight(1f)) {'
    new = 'Row(Modifier.fillMaxWidth().clickable { DetailNav.openStock(s.code, null) }) {\n                            Column(Modifier.weight(1f)) {'
    if old in rs:
        rs = rs.replace(old, new, 1)
    rs = rs.replace('Text("${s.sector} · ${s.action} · 追高${chaseZh25(s.chase)}",', 'Text("${s.sector} · ${s.action} · 追高风险${chaseZh25(s.chase)} · 点开查看并交易",')
    radar.write_text(rs, encoding='utf-8')

journal = root / 'TradeJournal.kt'
js = journal.read_text(encoding='utf-8')
if 'import androidx.compose.foundation.clickable' not in js:
    js = js.replace('import androidx.compose.foundation.layout.*\n', 'import androidx.compose.foundation.clickable\nimport androidx.compose.foundation.layout.*\n', 1)
js = js.replace('Text("我的交易日志"', 'Text("我的持仓与交易"')
js = js.replace('Text("本地保存 · 覆盖升级不丢 · 可导出备份"', 'Text("持仓收益 · 成本 · 可卖数量 · 成交记录均保存在本机"')
js = js.replace('Button(onClick = { showAdd = true }) { Text("记一笔", fontSize = 10.sp) }', 'OutlinedButton(onClick = { showAdd = true }) { Text("补录成交", fontSize = 10.sp) }')
js = js.replace('item { Text("当前持仓", fontWeight = FontWeight.Bold) }', 'item { Text("当前持仓与收益", fontWeight = FontWeight.Bold) }')
js = js.replace('item { Text("成交与收益记录", fontWeight = FontWeight.Bold) }', 'item { Text("历史成交与已实现收益", fontWeight = FontWeight.Bold) }')
old_call = 'JournalPositionCard(p, quotes[symbol(p.code)]) { sellPosition = p }'
new_call = 'JournalPositionCard(p, quotes[symbol(p.code)], onOpen = { DetailNav.openStock(p.code, null) }) { sellPosition = p }'
if old_call in js:
    js = js.replace(old_call, new_call, 1)
old_sig = 'private fun JournalPositionCard(p: LedgerPosition, q: Quote?, onSell: () -> Unit) {'
new_sig = 'private fun JournalPositionCard(p: LedgerPosition, q: Quote?, onOpen: () -> Unit, onSell: () -> Unit) {'
if old_sig in js:
    js = js.replace(old_sig, new_sig, 1)
fn = js.find(new_sig)
if fn >= 0:
    card = js.find('Card(shape = RoundedCornerShape(14.dp)) {', fn)
    if card >= 0:
        js = js[:card] + js[card:].replace('Card(shape = RoundedCornerShape(14.dp)) {', 'Card(Modifier.fillMaxWidth().clickable(onClick = onOpen), shape = RoundedCornerShape(14.dp)) {', 1)
    hint = 'Text("浮动盈亏 ${pnl?.let(::jMoneySigned) ?: "—"} · 首次买入 ${p.firstBuyDate ?: "—"}", fontSize = 9.sp, color = JournalMuted)'
    if hint in js and '点开查看行情并交易' not in js[fn:fn+3000]:
        js = js.replace(hint, hint + '\n            Text("点开查看行情、策略并交易", fontSize = 8.sp, color = JournalBlue)', 1)
journal.write_text(js, encoding='utf-8')

v6 = root / 'V6Activity.kt'
vs = v6.read_text(encoding='utf-8')
vs = vs.replace('TRADES("交易", Icons.Default.ViewList)', 'TRADES("持仓", Icons.Default.ViewList)')
vs = vs.replace('点开详情', '点开查看并交易')
vs = vs.replace('Text(key, fontSize = 10.sp, fontWeight = FontWeight.Bold, color = if (selected) Blue else Ink)\n            Text(label, fontSize = 8.sp, color = Muted, maxLines = 1)',
                'Text(label, fontSize = 9.sp, fontWeight = FontWeight.Bold, color = if (selected) Blue else Ink)\n            Text("（$key）", fontSize = 7.sp, color = Muted, maxLines = 1)')
v6.write_text(vs, encoding='utf-8')

g = Path('app/build.gradle.kts')
gs = g.read_text(encoding='utf-8')
gs = gs.replace('versionCode = 27', 'versionCode = 28')
gs = gs.replace('versionName = "2.5.0"', 'versionName = "2.6.0"')
if 'versionName = "2.6.0"' not in gs:
    raise SystemExit('v2.6 version bump failed')
g.write_text(gs, encoding='utf-8')

assert 'StockTradingPanel26(' in detail.read_text(encoding='utf-8')
assert '确认记录买入' in trade.read_text(encoding='utf-8')
assert '确认记录卖出' in trade.read_text(encoding='utf-8')
assert 'TRADES("持仓"' in v6.read_text(encoding='utf-8')
assert '我的持仓与交易' in journal.read_text(encoding='utf-8')
print('v2.6 Chinese stock-detail trading + holdings UI integrated')