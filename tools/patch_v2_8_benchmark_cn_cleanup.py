from pathlib import Path

root = Path('app/src/main/java/com/rui/astockstrategy/v6')
ui = root / 'V28AiShadowPortfolio.kt'
v6 = root / 'V6Activity.kt'
if not ui.exists() or not v6.exists():
    raise SystemExit('v2.8 generated UI files missing')

s = ui.read_text(encoding='utf-8')
repl = {
    'AI影子实盘组合': '智能影子实盘组合',
    'AI影子实盘数据暂未同步': '智能影子实盘数据暂未同步',
    '当前AI持仓': '当前智能持仓',
    'AI账户保持现金': '智能账户保持现金',
    '今日AI交易决策': '今日智能交易决策',
    'AI交易规则': '智能交易规则',
    'AI影子实盘仅用于策略验证': '智能影子实盘仅用于策略验证',
}
for a, b in repl.items():
    s = s.replace(a, b)

anchor = '        item { AiTitle28("当前智能持仓") }'
if anchor not in s:
    raise SystemExit('benchmark insertion anchor missing')
if 'AiBenchmarkCard28(d)' not in s:
    s = s.replace(anchor, '        item { AiBenchmarkCard28(d) }\n\n' + anchor, 1)

if 'private fun AiBenchmarkCard28' not in s:
    s += r'''

@Composable
private fun AiBenchmarkCard28(d: JSONObject?) {
    val b = d?.optJSONObject("benchmarkComparison")
    if (b == null) {
        Card(shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
            Column(Modifier.fillMaxWidth().padding(13.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("同期基准比较", fontWeight = FontWeight.Bold, fontSize = 14.sp)
                Text("基准将在下一次与主线雷达同步刷新时开始记录，不回填历史价格。", color = AiMuted28, fontSize = 9.sp)
            }
        }
        return
    }
    val started = b.optString("startedAt").replace("T", " ").take(16)
    val port = n28(b, "portfolioReturnPct")
    val indexes = b.optJSONArray("indexes")
    val pool = b.optJSONObject("candidatePool")
    Card(shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.fillMaxWidth().padding(13.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("同期基准比较", fontWeight = FontWeight.Bold, fontSize = 14.sp)
                    Text("起始 $started · 不事后倒填", color = AiMuted28, fontSize = 8.sp)
                }
                Text("智能组合 ${pct28(port)}", color = pnlColor28(port), fontWeight = FontWeight.Bold, fontSize = 11.sp)
            }
            HorizontalDivider()
            if (indexes != null) {
                for (i in 0 until indexes.length()) {
                    val x = indexes.optJSONObject(i) ?: continue
                    val r = n28(x, "returnPct")
                    val a = n28(x, "alphaPct")
                    Row {
                        Text(x.optString("name"), Modifier.weight(1f), fontSize = 10.sp)
                        Text("同期 ${pct28(r)}", Modifier.width(90.dp), color = pnlColor28(r), fontSize = 9.sp)
                        Text("超额 ${pct28(a)}", color = pnlColor28(a), fontWeight = FontWeight.Bold, fontSize = 9.sp)
                    }
                }
            }
            if (pool != null) {
                val r = n28(pool, "returnPct")
                val a = n28(pool, "alphaPct")
                Row {
                    Text("原始候选池等权（${pool.optInt("memberCount")}只）", Modifier.weight(1f), fontSize = 10.sp)
                    Text("同期 ${pct28(r)}", Modifier.width(90.dp), color = pnlColor28(r), fontSize = 9.sp)
                    Text("超额 ${pct28(a)}", color = pnlColor28(a), fontWeight = FontWeight.Bold, fontSize = 9.sp)
                }
                val definition = pool.optString("definitionZh")
                if (definition.isNotBlank()) Text(definition, color = AiMuted28, fontSize = 8.sp)
            }
            val note = b.optString("noteZh")
            if (note.isNotBlank()) Text(note, color = AiMuted28, fontSize = 8.sp)
        }
    }
}
'''

ui.write_text(s, encoding='utf-8')

vs = v6.read_text(encoding='utf-8')
vs = vs.replace('AI_SHADOW("AI实盘"', 'AI_SHADOW("智能实盘"')
v6.write_text(vs, encoding='utf-8')

assert 'AI_SHADOW("智能实盘"' in v6.read_text(encoding='utf-8')
assert 'AiBenchmarkCard28(d)' in ui.read_text(encoding='utf-8')
assert '今日智能交易决策' in ui.read_text(encoding='utf-8')
print('v2.8 benchmark comparison + final Chinese display cleanup applied')
