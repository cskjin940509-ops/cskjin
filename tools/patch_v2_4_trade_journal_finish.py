from pathlib import Path
import re

# patch_v2_4_trade_journal.py intentionally runs first and may stop after creating
# TradeJournal.kt. This finisher is structure-based and must be sufficient to finish
# the build regardless of earlier localization/formatting patches.

j = Path('app/src/main/java/com/rui/astockstrategy/v6/TradeJournal.kt')
if not j.exists() or 'object TradeLedger' not in j.read_text(encoding='utf-8'):
    raise SystemExit('TradeJournal.kt was not generated')

# -----------------------------------------------------------------------------
# 1) Add journal navigation using stable enum/when structural markers.
# -----------------------------------------------------------------------------
p = Path('app/src/main/java/com/rui/astockstrategy/v6/V6Activity.kt')
s = p.read_text(encoding='utf-8')
if 'TRADES("交易"' not in s:
    s, n = re.subn(
        r'(?m)^(\s*)HISTORY\(',
        r'\1TRADES("交易", Icons.Default.ViewList),\n\1HISTORY(',
        s,
        count=1,
    )
    if n != 1:
        raise SystemExit('cannot insert TRADES enum entry')
if 'Tab.TRADES -> TradeJournalScreen()' not in s:
    s, n = re.subn(
        r'(?m)^(\s*)Tab\.HISTORY\s*->',
        r'\1Tab.TRADES -> TradeJournalScreen()\n\1Tab.HISTORY ->',
        s,
        count=1,
    )
    if n != 1:
        raise SystemExit('cannot insert trade journal navigation')
p.write_text(s, encoding='utf-8')

# -----------------------------------------------------------------------------
# 2) Make local ledger T+1-aware and add sell-from-journal for positions that are no
# longer in the execution-candidate list.
# -----------------------------------------------------------------------------
js = j.read_text(encoding='utf-8')
if 'val sellableQty: Int' not in js:
    js = js.replace(
        '    val firstBuyDate: String?,\n)',
        '    val firstBuyDate: String?,\n    val sellableQty: Int,\n)',
        1,
    )
    js = js.replace(
        'data class State(var name: String = "", var qty: Int = 0, var cost: Double = 0.0, var first: String? = null)',
        'data class State(var name: String = "", var qty: Int = 0, var cost: Double = 0.0, var first: String? = null, var boughtBeforeToday: Int = 0, var soldQty: Int = 0)',
        1,
    )
    js = js.replace(
        'if (st.qty == 0) st.first = tradeDate(r.timestamp)\n                st.cost += r.price * r.qty + r.fee',
        'if (st.qty == 0) st.first = tradeDate(r.timestamp)\n                if (tradeDate(r.timestamp) < LocalDate.now(JournalZone).toString()) st.boughtBeforeToday += r.qty\n                st.cost += r.price * r.qty + r.fee',
        1,
    )
    js = js.replace(
        'st.cost -= basis\n                st.qty -= q',
        'st.cost -= basis\n                st.qty -= q\n                st.soldQty += q',
        1,
    )
    js = js.replace(
        'LedgerPosition(parts[1], st.name, parts[0], st.qty, st.cost, st.cost / st.qty, st.first)',
        'LedgerPosition(parts[1], st.name, parts[0], st.qty, st.cost, st.cost / st.qty, st.first, min(st.qty, (st.boughtBeforeToday - st.soldQty).coerceAtLeast(0)))',
        1,
    )

if 'var sellPosition by remember' not in js:
    js = js.replace(
        '    var showAdd by remember { mutableStateOf(false) }\n',
        '    var showAdd by remember { mutableStateOf(false) }\n    var sellPosition by remember { mutableStateOf<LedgerPosition?>(null) }\n',
        1,
    )
    js = js.replace(
        'items(summary.positions, key = { "${it.mode}:${it.code}" }) { p -> JournalPositionCard(p, quotes[symbol(p.code)]) }',
        'items(summary.positions, key = { "${it.mode}:${it.code}" }) { p -> JournalPositionCard(p, quotes[symbol(p.code)]) { sellPosition = p } }',
        1,
    )
    dialog_anchor = '''    if (showAdd) {\n        TradeRecordDialog(initialCode = "", initialName = "", initialPrice = null, side = "BUY", fixedMode = null,\n            maxQty = null, source = "手动记录", sourceDate = LocalDate.now(JournalZone).toString(), signal = null,\n            onDismiss = { showAdd = false }, onSaved = { showAdd = false; version++; message = "交易记录已保存" })\n    }\n'''
    dialog_extra = dialog_anchor + '''\n    sellPosition?.let { p ->\n        val live = quotes[symbol(p.code)]?.price\n        TradeRecordDialog(\n            initialCode = p.code, initialName = p.name, initialPrice = live ?: p.avgCost, side = "SELL",\n            fixedMode = p.mode, maxQty = p.sellableQty, source = "交易日志",\n            sourceDate = LocalDate.now(JournalZone).toString(), signal = "手动卖出记录",\n            onDismiss = { sellPosition = null },\n            onSaved = { sellPosition = null; version++; message = "卖出记录已保存，已实现收益已更新" }\n        )\n    }\n'''
    if dialog_anchor not in js:
        raise SystemExit('journal dialog anchor missing')
    js = js.replace(dialog_anchor, dialog_extra, 1)
    js = js.replace(
        'private fun JournalPositionCard(p: LedgerPosition, q: Quote?) {',
        'private fun JournalPositionCard(p: LedgerPosition, q: Quote?, onSell: () -> Unit) {',
        1,
    )
    pos_text = 'Text("浮动盈亏 ${pnl?.let(::jMoneySigned) ?: "—"} · 首次买入 ${p.firstBuyDate ?: "—"}", fontSize = 9.sp, color = JournalMuted)'
    pos_extra = pos_text + '''\n            Text("今日可卖 ${p.sellableQty}股 / 持仓 ${p.qty}股", fontSize = 8.sp, color = JournalMuted)\n            if (p.sellableQty > 0) {\n                TextButton(onClick = onSell, contentPadding = PaddingValues(0.dp), modifier = Modifier.height(27.dp)) { Text("记录卖出", fontSize = 9.sp) }\n            } else {\n                Text("当日新买部分按普通A股T+1规则不可卖", fontSize = 8.sp, color = JournalMuted)\n            }'''
    if pos_text not in js:
        raise SystemExit('journal position text anchor missing')
    js = js.replace(pos_text, pos_extra, 1)

j.write_text(js, encoding='utf-8')

# -----------------------------------------------------------------------------
# 3) Replace the old one-price LocalPosition marker in the execution assistant with
# the same durable ledger. This keeps recommendation signal and actual fill separate.
# -----------------------------------------------------------------------------
e = Path('app/src/main/java/com/rui/astockstrategy/v6/ExecutionPanel.kt')
es = e.read_text(encoding='utf-8')
es = es.replace('ExecutionStockCard(st, quotes[symbol(st.code)])', 'ExecutionStockCard(st, quotes[symbol(st.code)], s.date)')
es = es.replace('private fun ExecutionStockCard(st: ExecStock, q: Quote?) {', 'private fun ExecutionStockCard(st: ExecStock, q: Quote?, signalDate: String) {')

fn = es.find('private fun ExecutionStockCard(st: ExecStock, q: Quote?, signalDate: String) {')
if fn < 0:
    raise SystemExit('ExecutionStockCard signature missing')
a = es.find('    val context = LocalContext.current', fn)
b = es.find('    val actionColor = when', a)
if a < 0 or b < 0:
    raise SystemExit('execution state structural markers missing')
new_state = '''    val context = LocalContext.current\n    var ledgerVersion by remember(st.code) { mutableIntStateOf(0) }\n    var dialogSide by remember(st.code) { mutableStateOf<String?>(null) }\n    val realPos = remember(st.code, ledgerVersion) { TradeLedger.position(context, st.code, "REAL") }\n    val paperPos = remember(st.code, ledgerVersion) { TradeLedger.position(context, st.code, "PAPER") }\n    val pos = realPos ?: paperPos\n\n    val live = q?.price ?: st.price\n    val change = q?.change ?: st.changePct\n    val high = q?.high ?: st.dayHigh\n    val low = q?.low ?: st.dayLow\n    val pnlPct = if (pos != null && live != null && pos.costBasis > 0) (live * pos.qty / pos.costBasis - 1.0) * 100.0 else null\n\n'''
es = es[:a] + new_state + es[b:]

start = es.find('            if (pos == null) {', fn)
end_marker = '\n        }\n    }\n}\n\nprivate suspend fun fetchExecutionSnapshot'
end = es.find(end_marker, start)
if start < 0 or end < 0:
    raise SystemExit('execution position UI structural markers missing')
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
                            if (pos.sellableQty <= 0) "今日没有可卖数量：普通A股按T+1约束。"
                            else "持仓判断：${st.holdingAction ?: "持有观察"} · ${st.holdingReason ?: "未触发保护条件"}",
                            fontSize = 9.sp,
                            color = Color(0xFF5F6874)
                        )
                        Text("今日可卖 ${pos.sellableQty}股", fontSize = 8.sp, color = Color(0xFF6D7480))
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            TextButton(onClick = { dialogSide = "BUY" }, contentPadding = PaddingValues(0.dp), modifier = Modifier.height(28.dp)) { Text("记录加仓", fontSize = 9.sp) }
                            TextButton(onClick = { if (pos.sellableQty > 0) dialogSide = "SELL" }, enabled = pos.sellableQty > 0, contentPadding = PaddingValues(0.dp), modifier = Modifier.height(28.dp)) { Text("记录卖出", fontSize = 9.sp) }
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
                    maxQty = if (side == "SELL") pos?.sellableQty else null,
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

# -----------------------------------------------------------------------------
# 4) Final version bump + assertions.
# -----------------------------------------------------------------------------
g = Path('app/build.gradle.kts')
gs = g.read_text(encoding='utf-8')
gs = gs.replace('versionCode = 25', 'versionCode = 26')
gs = gs.replace('versionName = "2.3.0"', 'versionName = "2.4.0"')
if 'versionName = "2.4.0"' not in gs:
    raise SystemExit('v2.4 version bump failed')
g.write_text(gs, encoding='utf-8')

assert 'Tab.TRADES -> TradeJournalScreen()' in p.read_text(encoding='utf-8')
assert 'sellableQty' in j.read_text(encoding='utf-8')
assert 'TradeLedger.position' in e.read_text(encoding='utf-8')
print('v2.4 trade journal integration finished')
