from pathlib import Path

journal = r'''package com.rui.astockstrategy.v6

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import kotlinx.coroutines.delay
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.UUID
import kotlin.math.abs
import kotlin.math.min

private val JournalZone = ZoneId.of("Asia/Shanghai")
private const val JournalPrefs = "astock_trade_journal_v1"
private const val JournalKey = "records_json"
private val JournalRed = Color(0xFFD54432)
private val JournalGreen = Color(0xFF16855B)
private val JournalBlue = Color(0xFF3567B7)
private val JournalMuted = Color(0xFF6D7480)

data class TradeRecord(
    val id: String,
    val code: String,
    val name: String,
    val side: String,
    val mode: String,
    val timestamp: Long,
    val price: Double,
    val qty: Int,
    val fee: Double,
    val source: String,
    val sourceDate: String?,
    val signal: String?,
    val note: String?,
    val realizedPnl: Double?,
    val realizedPct: Double?,
    val soldCostBasis: Double?,
)

data class LedgerPosition(
    val code: String,
    val name: String,
    val mode: String,
    val qty: Int,
    val costBasis: Double,
    val avgCost: Double,
    val firstBuyDate: String?,
)

data class LedgerSummary(
    val positions: List<LedgerPosition>,
    val realizedPnl: Double,
    val soldCostBasis: Double,
    val totalFees: Double,
    val tradeCount: Int,
)

object TradeLedger {
    private fun prefs(context: Context) = context.getSharedPreferences(JournalPrefs, Context.MODE_PRIVATE)

    fun records(context: Context): List<TradeRecord> {
        val raw = prefs(context).getString(JournalKey, "[]") ?: "[]"
        return runCatching {
            val a = JSONArray(raw)
            (0 until a.length()).mapNotNull { i -> fromJson(a.optJSONObject(i)) }.sortedBy { it.timestamp }
        }.getOrElse { emptyList() }
    }

    private fun save(context: Context, rows: List<TradeRecord>) {
        val a = JSONArray()
        rows.sortedBy { it.timestamp }.forEach { a.put(toJson(it)) }
        prefs(context).edit().putString(JournalKey, a.toString()).apply()
    }

    fun exportJson(context: Context): String {
        val a = JSONArray()
        records(context).forEach { a.put(toJson(it)) }
        return JSONObject().put("schemaVersion", 1).put("exportedAt", LocalDateTime.now(JournalZone).toString()).put("records", a).toString(2)
    }

    fun importMerge(context: Context, text: String): Int {
        val root = JSONObject(text)
        val a = root.optJSONArray("records") ?: JSONArray()
        val incoming = (0 until a.length()).mapNotNull { i -> fromJson(a.optJSONObject(i)) }
        val old = records(context)
        val ids = old.map { it.id }.toMutableSet()
        val merged = old.toMutableList()
        incoming.forEach { if (ids.add(it.id)) merged.add(it) }
        save(context, merged)
        return merged.size - old.size
    }

    fun delete(context: Context, id: String) {
        save(context, records(context).filterNot { it.id == id })
    }

    fun position(context: Context, code: String, mode: String? = null): LedgerPosition? =
        summary(context, mode).positions.firstOrNull { it.code == code }

    fun add(
        context: Context,
        code: String,
        name: String,
        side: String,
        mode: String,
        price: Double,
        qty: Int,
        fee: Double,
        source: String,
        sourceDate: String?,
        signal: String?,
        note: String?,
    ): TradeRecord {
        require(code.isNotBlank()) { "股票代码不能为空" }
        require(price > 0) { "成交价格必须大于0" }
        require(qty > 0) { "成交数量必须大于0" }
        require(fee >= 0) { "手续费不能为负数" }
        val before = summary(context, mode).positions.firstOrNull { it.code == code }
        var realized: Double? = null
        var realizedPct: Double? = null
        var soldBasis: Double? = null
        if (side == "SELL") {
            require(before != null && before.qty >= qty) { "卖出数量超过当前记录持仓" }
            soldBasis = before.avgCost * qty
            realized = price * qty - fee - soldBasis
            realizedPct = if (soldBasis > 0) realized / soldBasis * 100.0 else null
        }
        val row = TradeRecord(
            id = UUID.randomUUID().toString(), code = code.trim(), name = name.ifBlank { code.trim() },
            side = side, mode = mode, timestamp = System.currentTimeMillis(), price = price, qty = qty, fee = fee,
            source = source, sourceDate = sourceDate, signal = signal, note = note,
            realizedPnl = realized, realizedPct = realizedPct, soldCostBasis = soldBasis,
        )
        save(context, records(context) + row)
        return row
    }

    fun summary(context: Context, mode: String? = null): LedgerSummary {
        val rows = records(context).filter { mode == null || it.mode == mode }
        data class State(var name: String = "", var qty: Int = 0, var cost: Double = 0.0, var first: String? = null)
        val states = linkedMapOf<String, State>()
        var realized = 0.0
        var soldBasis = 0.0
        var fees = 0.0
        rows.forEach { r ->
            fees += r.fee
            val key = "${r.mode}:${r.code}"
            val st = states.getOrPut(key) { State(name = r.name) }
            st.name = r.name
            if (r.side == "BUY") {
                if (st.qty == 0) st.first = tradeDate(r.timestamp)
                st.cost += r.price * r.qty + r.fee
                st.qty += r.qty
            } else if (r.side == "SELL" && st.qty > 0) {
                val q = min(r.qty, st.qty)
                val avg = if (st.qty > 0) st.cost / st.qty else 0.0
                val basis = avg * q
                realized += r.price * q - r.fee - basis
                soldBasis += basis
                st.cost -= basis
                st.qty -= q
                if (st.qty <= 0) { st.qty = 0; st.cost = 0.0; st.first = null }
            }
        }
        val positions = states.mapNotNull { (key, st) ->
            if (st.qty <= 0) return@mapNotNull null
            val parts = key.split(":", limit = 2)
            LedgerPosition(parts[1], st.name, parts[0], st.qty, st.cost, st.cost / st.qty, st.first)
        }.sortedWith(compareBy<LedgerPosition> { it.mode }.thenBy { it.code })
        return LedgerSummary(positions, realized, soldBasis, fees, rows.size)
    }

    private fun toJson(r: TradeRecord) = JSONObject()
        .put("id", r.id).put("code", r.code).put("name", r.name).put("side", r.side).put("mode", r.mode)
        .put("timestamp", r.timestamp).put("price", r.price).put("qty", r.qty).put("fee", r.fee)
        .put("source", r.source).put("sourceDate", r.sourceDate).put("signal", r.signal).put("note", r.note)
        .put("realizedPnl", r.realizedPnl).put("realizedPct", r.realizedPct).put("soldCostBasis", r.soldCostBasis)

    private fun fromJson(o: JSONObject?): TradeRecord? {
        o ?: return null
        val id = o.optString("id")
        val code = o.optString("code")
        val price = o.optDouble("price", Double.NaN)
        val qty = o.optInt("qty", 0)
        if (id.isBlank() || code.isBlank() || !price.isFinite() || price <= 0 || qty <= 0) return null
        fun n(key: String): Double? = o.opt(key).let { v -> when (v) { null, JSONObject.NULL -> null; is Number -> v.toDouble(); else -> v.toString().toDoubleOrNull() } }
        return TradeRecord(
            id, code, o.optString("name", code), o.optString("side", "BUY"), o.optString("mode", "REAL"),
            o.optLong("timestamp", 0L), price, qty, o.optDouble("fee", 0.0), o.optString("source", "手动记录"),
            o.optString("sourceDate").takeIf { it.isNotBlank() }, o.optString("signal").takeIf { it.isNotBlank() },
            o.optString("note").takeIf { it.isNotBlank() }, n("realizedPnl"), n("realizedPct"), n("soldCostBasis")
        )
    }
}

@Composable
fun TradeJournalScreen() {
    val context = LocalContext.current
    var version by remember { mutableIntStateOf(0) }
    var mode by remember { mutableStateOf("REAL") }
    var showAdd by remember { mutableStateOf(false) }
    var quotes by remember { mutableStateOf<Map<String, Quote>>(emptyMap()) }
    var message by remember { mutableStateOf<String?>(null) }
    val records = remember(version) { TradeLedger.records(context) }
    val summary = remember(version, mode) { TradeLedger.summary(context, mode) }

    LaunchedEffect(version, mode) {
        while (true) {
            val codes = TradeLedger.summary(context, mode).positions.map { symbol(it.code) }
            if (codes.isNotEmpty()) runCatching { DataApi.fetchQuotes(codes) }.onSuccess { if (it.isNotEmpty()) quotes = it }
            delay(5_000)
        }
    }

    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("我的交易日志", fontWeight = FontWeight.Bold, fontSize = 19.sp)
                    Text("本地保存 · 覆盖升级不丢 · 可导出备份", fontSize = 9.sp, color = JournalMuted)
                }
                Button(onClick = { showAdd = true }) { Text("记一笔", fontSize = 10.sp) }
            }
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(selected = mode == "REAL", onClick = { mode = "REAL" }, label = { Text("实盘") })
                FilterChip(selected = mode == "PAPER", onClick = { mode = "PAPER" }, label = { Text("模拟") })
            }
        }
        item { JournalSummaryCard(summary, quotes) }
        message?.let { item { Text(it, fontSize = 9.sp, color = JournalBlue) } }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = {
                    val cm = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                    cm.setPrimaryClip(ClipData.newPlainText("A股交易日志备份", TradeLedger.exportJson(context)))
                    message = "已复制交易日志备份到剪贴板"
                }, modifier = Modifier.weight(1f)) { Text("复制备份", fontSize = 9.sp) }
                OutlinedButton(onClick = {
                    val cm = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                    val text = cm.primaryClip?.getItemAt(0)?.coerceToText(context)?.toString().orEmpty()
                    val added = runCatching { TradeLedger.importMerge(context, text) }.getOrElse { -1 }
                    if (added >= 0) { version++; message = "备份导入完成，新增${added}笔" } else message = "剪贴板不是有效交易日志备份"
                }, modifier = Modifier.weight(1f)) { Text("导入备份", fontSize = 9.sp) }
            }
        }
        item { Text("当前持仓", fontWeight = FontWeight.Bold) }
        if (summary.positions.isEmpty()) item { Text("暂无${if (mode == "REAL") "实盘" else "模拟"}持仓", fontSize = 11.sp, color = JournalMuted) }
        items(summary.positions, key = { "${it.mode}:${it.code}" }) { p -> JournalPositionCard(p, quotes[symbol(p.code)]) }
        item { Text("成交与收益记录", fontWeight = FontWeight.Bold) }
        val visible = records.filter { it.mode == mode }.sortedByDescending { it.timestamp }
        if (visible.isEmpty()) item { Text("还没有成交记录", fontSize = 11.sp, color = JournalMuted) }
        items(visible, key = { it.id }) { r ->
            JournalTradeRow(r) { TradeLedger.delete(context, r.id); version++; message = "已删除该笔记录并重新计算收益" }
        }
        item { Text("收益按移动平均成本计算；手续费以你录入值为准。交易日志用于记录与复盘，不等同于券商交割单。", fontSize = 8.sp, color = JournalMuted) }
    }

    if (showAdd) {
        TradeRecordDialog(initialCode = "", initialName = "", initialPrice = null, side = "BUY", fixedMode = null,
            maxQty = null, source = "手动记录", sourceDate = LocalDate.now(JournalZone).toString(), signal = null,
            onDismiss = { showAdd = false }, onSaved = { showAdd = false; version++; message = "交易记录已保存" })
    }
}

@Composable
private fun JournalSummaryCard(s: LedgerSummary, quotes: Map<String, Quote>) {
    var unrealized = 0.0
    var marketValue = 0.0
    s.positions.forEach { p ->
        val px = quotes[symbol(p.code)]?.price
        if (px != null) { marketValue += px * p.qty; unrealized += px * p.qty - p.costBasis }
    }
    val total = s.realizedPnl + unrealized
    Card(shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = Color(0xFFF8FAFF))) {
        Column(Modifier.fillMaxWidth().padding(13.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("收益概览", fontWeight = FontWeight.Bold)
            JournalKey("已实现盈亏", jMoneySigned(s.realizedPnl), if (s.realizedPnl >= 0) JournalRed else JournalGreen)
            JournalKey("未实现盈亏", jMoneySigned(unrealized), if (unrealized >= 0) JournalRed else JournalGreen)
            JournalKey("合计盈亏", jMoneySigned(total), if (total >= 0) JournalRed else JournalGreen)
            JournalKey("当前市值", jMoney(marketValue), JournalMuted)
            JournalKey("累计手续费", jMoney(s.totalFees), JournalMuted)
            JournalKey("成交笔数", "${s.tradeCount}", JournalMuted)
        }
    }
}

@Composable
private fun JournalPositionCard(p: LedgerPosition, q: Quote?) {
    val px = q?.price
    val pnl = if (px != null) px * p.qty - p.costBasis else null
    val pct = if (pnl != null && p.costBasis > 0) pnl / p.costBasis * 100.0 else null
    Card(shape = RoundedCornerShape(14.dp)) {
        Column(Modifier.fillMaxWidth().padding(11.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Row {
                Column(Modifier.weight(1f)) { Text("${p.name} ${p.code}", fontWeight = FontWeight.Bold); Text("${p.qty}股 · 平均成本 ${String.format("%.3f", p.avgCost)}", fontSize = 9.sp, color = JournalMuted) }
                Column(horizontalAlignment = Alignment.End) { Text(px?.let { String.format("%.2f", it) } ?: "—", fontWeight = FontWeight.Bold); Text(pct?.let { String.format("%+.2f%%", it) } ?: "—", fontSize = 10.sp, color = if ((pnl ?: 0.0) >= 0) JournalRed else JournalGreen) }
            }
            Text("浮动盈亏 ${pnl?.let(::jMoneySigned) ?: "—"} · 首次买入 ${p.firstBuyDate ?: "—"}", fontSize = 9.sp, color = JournalMuted)
        }
    }
}

@Composable
private fun JournalTradeRow(r: TradeRecord, onDelete: () -> Unit) {
    Card(shape = RoundedCornerShape(14.dp)) {
        Column(Modifier.fillMaxWidth().padding(10.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Row {
                Column(Modifier.weight(1f)) { Text("${if (r.side == "BUY") "买入" else "卖出"} ${r.name} ${r.code}", fontWeight = FontWeight.Bold, color = if (r.side == "BUY") JournalRed else JournalGreen); Text(tradeTime(r.timestamp), fontSize = 8.sp, color = JournalMuted) }
                Text("${r.qty}股 @ ${String.format("%.3f", r.price)}", fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
            }
            Text("手续费 ${String.format("%.2f", r.fee)} · ${if (r.mode == "REAL") "实盘" else "模拟"} · ${r.source}${r.signal?.let { " · $it" } ?: ""}", fontSize = 8.sp, color = JournalMuted)
            if (r.side == "SELL" && r.realizedPnl != null) Text("该笔已实现 ${jMoneySigned(r.realizedPnl)} (${r.realizedPct?.let { String.format("%+.2f%%", it) } ?: "—"})", fontSize = 9.sp, color = if (r.realizedPnl >= 0) JournalRed else JournalGreen)
            r.note?.let { Text(it, fontSize = 8.sp, color = JournalMuted, maxLines = 2) }
            TextButton(onClick = onDelete, contentPadding = PaddingValues(0.dp), modifier = Modifier.height(25.dp)) { Text("删除/纠错", fontSize = 8.sp) }
        }
    }
}

@Composable
fun TradeRecordDialog(
    initialCode: String,
    initialName: String,
    initialPrice: Double?,
    side: String,
    fixedMode: String?,
    maxQty: Int?,
    source: String,
    sourceDate: String?,
    signal: String?,
    onDismiss: () -> Unit,
    onSaved: (TradeRecord) -> Unit,
) {
    val context = LocalContext.current
    var code by remember { mutableStateOf(initialCode) }
    var name by remember { mutableStateOf(initialName) }
    var price by remember { mutableStateOf(initialPrice?.let { String.format("%.3f", it) } ?: "") }
    var qty by remember { mutableStateOf((maxQty ?: 100).toString()) }
    var fee by remember { mutableStateOf("0") }
    var mode by remember { mutableStateOf(fixedMode ?: "REAL") }
    var note by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (side == "BUY") "记录买入" else "记录卖出") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
                if (initialCode.isBlank()) OutlinedTextField(code, { code = it.filter(Char::isDigit).take(6) }, label = { Text("股票代码") }, singleLine = true)
                if (initialName.isBlank()) OutlinedTextField(name, { name = it }, label = { Text("股票名称") }, singleLine = true)
                OutlinedTextField(price, { price = it }, label = { Text("实际成交价") }, singleLine = true)
                OutlinedTextField(qty, { qty = it.filter(Char::isDigit) }, label = { Text("数量(股)") }, singleLine = true)
                OutlinedTextField(fee, { fee = it }, label = { Text("手续费/税费") }, singleLine = true)
                if (fixedMode == null) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(selected = mode == "REAL", onClick = { mode = "REAL" }, label = { Text("实盘") })
                    FilterChip(selected = mode == "PAPER", onClick = { mode = "PAPER" }, label = { Text("模拟") })
                }
                OutlinedTextField(note, { note = it }, label = { Text("备注（可选）") }, minLines = 2)
                Text("来源：$source${signal?.let { " · $it" } ?: ""}${sourceDate?.let { " · $it" } ?: ""}", fontSize = 8.sp, color = JournalMuted)
                error?.let { Text(it, color = JournalGreen, fontSize = 9.sp) }
            }
        },
        confirmButton = {
            Button(onClick = {
                val p = price.toDoubleOrNull(); val q = qty.toIntOrNull(); val f = fee.toDoubleOrNull() ?: 0.0
                val result = runCatching { TradeLedger.add(context, code, name, side, mode, p ?: -1.0, q ?: 0, f, source, sourceDate, signal, note.takeIf { it.isNotBlank() }) }
                result.onSuccess(onSaved).onFailure { error = it.message ?: "保存失败" }
            }) { Text("保存") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("取消") } }
    )
}

@Composable
private fun JournalKey(k: String, v: String, color: Color) { Row(Modifier.fillMaxWidth()) { Text(k, Modifier.weight(1f), fontSize = 9.sp, color = JournalMuted); Text(v, fontSize = 10.sp, fontWeight = FontWeight.SemiBold, color = color) } }
private fun tradeDate(ts: Long) = Instant.ofEpochMilli(ts).atZone(JournalZone).toLocalDate().toString()
private fun tradeTime(ts: Long) = Instant.ofEpochMilli(ts).atZone(JournalZone).format(DateTimeFormatter.ofPattern("MM-dd HH:mm:ss"))
private fun jMoney(v: Double) = when { abs(v) >= 1e8 -> String.format("%.2f亿", v/1e8); abs(v) >= 1e4 -> String.format("%.2f万", v/1e4); else -> String.format("%.2f", v) }
private fun jMoneySigned(v: Double) = (if (v >= 0) "+" else "") + jMoney(v)
'''

Path('app/src/main/java/com/rui/astockstrategy/v6/TradeJournal.kt').write_text(journal, encoding='utf-8')

# Add a dedicated journal tab after all prior UI patches.
p = Path('app/src/main/java/com/rui/astockstrategy/v6/V6Activity.kt')
s = p.read_text(encoding='utf-8')
if 'TRADES("交易"' not in s:
    s = s.replace('    POOLS("股票池", Icons.Default.ViewList),\n    HISTORY(', '    POOLS("股票池", Icons.Default.ViewList),\n    TRADES("交易", Icons.Default.ViewList),\n    HISTORY(', 1)
if 'Tab.TRADES -> TradeJournalScreen()' not in s:
    s = s.replace('                    Tab.POOLS -> PoolsScreen(active, quotes, tick, quoteOkAt)\n                    Tab.HISTORY', '                    Tab.POOLS -> PoolsScreen(active, quotes, tick, quoteOkAt)\n                    Tab.TRADES -> TradeJournalScreen()\n                    Tab.HISTORY', 1)
p.write_text(s, encoding='utf-8')

# Upgrade execution-card one-tap position marker to a full persisted trade record.
e = Path('app/src/main/java/com/rui/astockstrategy/v6/ExecutionPanel.kt')
es = e.read_text(encoding='utf-8')
es = es.replace('ExecutionStockCard(st, quotes[symbol(st.code)])', 'ExecutionStockCard(st, quotes[symbol(st.code)], s.date)')
es = es.replace('private fun ExecutionStockCard(st: ExecStock, q: Quote?) {', 'private fun ExecutionStockCard(st: ExecStock, q: Quote?, signalDate: String) {')
old_state = '''    val context = LocalContext.current\n    val prefs = remember { context.getSharedPreferences("astock_local_positions", Context.MODE_PRIVATE) }\n    var pos by remember(st.code) { mutableStateOf(loadPosition(prefs, st.code)) }\n\n    val live = q?.price ?: st.price\n    val change = q?.change ?: st.changePct\n    val high = q?.high ?: st.dayHigh\n    val low = q?.low ?: st.dayLow\n    val today = LocalDate.now(CnZone).toString()\n    val sellable = pos != null && pos!!.date < today\n    val pnlPct = if (pos != null && live != null && pos!!.price > 0) (live / pos!!.price - 1.0) * 100.0 else null\n'''
new_state = '''    val context = LocalContext.current\n    var ledgerVersion by remember(st.code) { mutableIntStateOf(0) }\n    var dialogSide by remember(st.code) { mutableStateOf<String?>(null) }\n    val realPos = remember(st.code, ledgerVersion) { TradeLedger.position(context, st.code, "REAL") }\n    val paperPos = remember(st.code, ledgerVersion) { TradeLedger.position(context, st.code, "PAPER") }\n    val pos = realPos ?: paperPos\n\n    val live = q?.price ?: st.price\n    val change = q?.change ?: st.changePct\n    val high = q?.high ?: st.dayHigh\n    val low = q?.low ?: st.dayLow\n    val today = LocalDate.now(CnZone).toString()\n    val sellable = pos != null && (pos.firstBuyDate ?: today) < today\n    val pnlPct = if (pos != null && live != null && pos.costBasis > 0) (live * pos.qty / pos.costBasis - 1.0) * 100.0 else null\n'''
if old_state in es:
    es = es.replace(old_state, new_state, 1)
else:
    raise SystemExit('execution state block not found')
start = es.find('            if (pos == null) {')
end = es.find('        }\n    }\n}\n\nprivate suspend fun fetchExecutionSnapshot', start)
if start < 0 or end < 0:
    raise SystemExit('execution position UI block not found')
replacement = r'''            if (pos == null) {
                Button(
                    onClick = { if (live != null && live > 0) dialogSide = "BUY" },
                    enabled = live != null && live > 0,
                    contentPadding = PaddingValues(horizontal = 10.dp, vertical = 2.dp),
                    modifier = Modifier.height(32.dp)
                ) { Text("记录我的买入", fontSize = 9.sp) }
            } else {
                Surface(color = Color(0xFFFFF7E7), shape = RoundedCornerShape(9.dp)) {
                    Column(Modifier.fillMaxWidth().padding(7.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text("我的${if (pos.mode == "REAL") "实盘" else "模拟"}持仓 ${pos.qty}股 · 成本 ${fmt(pos.avgCost)}", fontSize = 9.sp, fontWeight = FontWeight.Bold)
                        Text("当前浮动收益 ${signedPct(pnlPct)}", fontSize = 10.sp, color = if ((pnlPct ?: 0.0) >= 0) Color(0xFFD54432) else Color(0xFF16855B))
                        Text(
                            if (!sellable) "今日新仓：按普通A股T+1约束，今天不把离场提示当作可执行卖出。"
                            else "持仓判断：${st.holdingAction ?: "持有观察"} · ${st.holdingReason ?: "未触发保护条件"}",
                            fontSize = 9.sp,
                            color = Color(0xFF5F6874)
                        )
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            TextButton(onClick = { dialogSide = "BUY" }, contentPadding = PaddingValues(0.dp), modifier = Modifier.height(28.dp)) { Text("记录加仓", fontSize = 9.sp) }
                            TextButton(onClick = { if (sellable) dialogSide = "SELL" }, enabled = sellable, contentPadding = PaddingValues(0.dp), modifier = Modifier.height(28.dp)) { Text("记录卖出", fontSize = 9.sp) }
                        }
                    }
                }
            }

            if (dialogSide != null) {
                val side = dialogSide!!
                TradeRecordDialog(
                    initialCode = st.code,
                    initialName = st.name,
                    initialPrice = live,
                    side = side,
                    fixedMode = if (side == "SELL") pos?.mode else null,
                    maxQty = if (side == "SELL") pos?.qty else null,
                    source = sourceZh(st.source),
                    sourceDate = signalDate,
                    signal = if (side == "BUY") st.entryAction else st.holdingAction,
                    onDismiss = { dialogSide = null },
                    onSaved = { dialogSide = null; ledgerVersion++ }
                )
            }
'''
es = es[:start] + replacement + es[end:]
e.write_text(es, encoding='utf-8')

# Final version bump.
g = Path('app/build.gradle.kts')
gs = g.read_text(encoding='utf-8')
gs = gs.replace('versionCode = 25', 'versionCode = 26')
gs = gs.replace('versionName = "2.3.0"', 'versionName = "2.4.0"')
g.write_text(gs, encoding='utf-8')
