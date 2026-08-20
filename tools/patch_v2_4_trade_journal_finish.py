from pathlib import Path

# The first v2.4 patch creates TradeJournal.kt and the journal tab before it reaches
# the legacy execution-position block. Finish that integration using structural
# markers so earlier localization patches cannot break it.
j = Path('app/src/main/java/com/rui/astockstrategy/v6/TradeJournal.kt')
if not j.exists() or 'object TradeLedger' not in j.read_text(encoding='utf-8'):
    raise SystemExit('TradeJournal.kt was not generated')

p = Path('app/src/main/java/com/rui/astockstrategy/v6/V6Activity.kt')
s = p.read_text(encoding='utf-8')
if 'TRADES("交易"' not in s or 'Tab.TRADES -> TradeJournalScreen()' not in s:
    raise SystemExit('trade journal tab missing')

# Execution panel: previous patch already adjusted call/signature before its expected
# failure. Make those replacements idempotent in case this script is reused alone.
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
new_state = '''    val context = LocalContext.current\n    var ledgerVersion by remember(st.code) { mutableIntStateOf(0) }\n    var dialogSide by remember(st.code) { mutableStateOf<String?>(null) }\n    val realPos = remember(st.code, ledgerVersion) { TradeLedger.position(context, st.code, "REAL") }\n    val paperPos = remember(st.code, ledgerVersion) { TradeLedger.position(context, st.code, "PAPER") }\n    val pos = realPos ?: paperPos\n\n    val live = q?.price ?: st.price\n    val change = q?.change ?: st.changePct\n    val high = q?.high ?: st.dayHigh\n    val low = q?.low ?: st.dayLow\n    val today = LocalDate.now(java.time.ZoneId.of("Asia/Shanghai")).toString()\n    val sellable = pos != null && (pos.firstBuyDate ?: today) < today\n    val pnlPct = if (pos != null && live != null && pos.costBasis > 0) (live * pos.qty / pos.costBasis - 1.0) * 100.0 else null\n\n'''
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

# v2.3 is the previous final version.
g = Path('app/build.gradle.kts')
gs = g.read_text(encoding='utf-8')
gs = gs.replace('versionCode = 25', 'versionCode = 26')
gs = gs.replace('versionName = "2.3.0"', 'versionName = "2.4.0"')
if 'versionName = "2.4.0"' not in gs:
    raise SystemExit('v2.4 version bump failed')
g.write_text(gs, encoding='utf-8')
print('v2.4 trade journal integration finished')
