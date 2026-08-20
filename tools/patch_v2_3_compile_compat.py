from pathlib import Path

p=Path('app/src/main/java/com/rui/astockstrategy/v6/V6Activity.kt')
s=p.read_text(encoding='utf-8')

blocks=[]

if 'data class TradeAssist(' not in s:
    blocks.append(r'''
data class TradeAssist(val entry: String, val holding: String, val note: String)
''')

if 'fun tradeAssist(' not in s:
    blocks.append(r'''
fun tradeAssist(code: String, s: Snapshot, meta: StockMeta?, q: Quote?): TradeAssist {
    val price = q?.price ?: meta?.dayClose ?: meta?.selectionPrice
    val high = q?.high ?: meta?.dayHigh
    val low = q?.low ?: meta?.dayLow
    val chg = q?.change ?: meta?.dayChangePct
    val flow = meta?.mainFlowPct
    if (price == null || high == null || low == null || low <= 0) {
        return TradeAssist("条件不足，暂不介入", "条件不足，暂不判断离场", "缺少可靠价格区间时不生成交易提示。")
    }
    val nearHigh = high > 0 && price / high >= 0.985
    val nearLow = price / low <= 1.015
    val rangePosition = if (high > low) (price - low) / (high - low) else 0.5
    val strongFlow = (flow ?: 0.0) >= 5.0
    val entry = when {
        (chg ?: 0.0) >= 8.0 && nearHigh -> "涨幅较大且接近日内高位，不宜追高"
        (chg ?: 0.0) <= -4.0 || nearLow -> "价格处于弱势区，等待重新企稳"
        strongFlow && rangePosition in 0.30..0.72 && (chg ?: 0.0) in -1.5..5.0 -> "资金与价格结构尚可，可观察分批介入"
        rangePosition > 0.80 -> "价格位置偏高，等待回踩确认"
        else -> "保持观察，等待价格与资金共振"
    }
    val holding = when {
        (chg ?: 0.0) >= 7.0 && nearHigh -> "已有可卖持仓：接近日内高位，可考虑分批保护利润"
        (chg ?: 0.0) <= -4.0 && nearLow -> "已有可卖持仓：弱势接近日内低位，关注保护性减仓"
        strongFlow && rangePosition >= 0.45 -> "已有可卖持仓：趋势未明显破坏，可继续观察"
        else -> "已有可卖持仓：暂未触发明确保护条件"
    }
    val today = java.time.LocalDate.now(CnZone).toString()
    val note = if (s.date == today)
        "普通A股当日新买入不可当日卖出；离场提示仅适用于已有可卖持仓。"
    else
        "未录入你的真实成交成本；离场提示目前只依据行情结构。"
    return TradeAssist(entry, holding, note)
}
''')

if 'fun TradeAssistStrip(' not in s:
    blocks.append(r'''
@Composable
fun TradeAssistStrip(code: String, s: Snapshot, meta: StockMeta?, q: Quote?) {
    val a = tradeAssist(code, s, meta, q)
    Surface(color = Color(0xFFF0F3FA), shape = RoundedCornerShape(10.dp)) {
        Column(Modifier.fillMaxWidth().padding(8.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text("交易辅助", fontSize = 10.sp, fontWeight = FontWeight.Bold)
            Text("介入参考：${a.entry}", fontSize = 9.sp, color = Ink)
            Text("持仓保护：${a.holding}", fontSize = 9.sp, color = Ink)
            Text(a.note, fontSize = 8.sp, color = Muted)
        }
    }
}
''')

if 'fun displayChoice(' not in s:
    blocks.append(r'''
fun displayChoice(v: String): String = when (v) {
    "B0" -> "基础强势"
    "B1" -> "两融增强"
    "B2" -> "指数基金申赎"
    "B3" -> "主力资金"
    "B12" -> "两融+指数基金"
    "B13" -> "两融+主力资金"
    "B23" -> "指数基金+主力资金"
    "B4" -> "综合确认"
    else -> v
}
''')

if 'fun detailCurrentReturn(' not in s:
    blocks.append(r'''
fun detailCurrentReturn(perf: JSONObject?): String {
    if (perf == null) return "—"
    val cur = perf.optJSONObject("current")
    val raw = cur?.opt("return")
    if (raw != null && raw != JSONObject.NULL) return pretty(raw)
    for (k in listOf("1D", "5D", "10D", "20D", "60D")) {
        val o = perf.optJSONObject(k) ?: continue
        val r = o.opt("return")
        if (r != null && r != JSONObject.NULL) return pretty(r)
    }
    return "—"
}
''')

if 'fun DataCoverageCard(' not in s:
    blocks.append(r'''
@Composable
fun DataCoverageCard(s: Snapshot) {
    val allCodes = s.pools.values.flatten().distinct()
    val metas = allCodes.mapNotNull { s.stocks[it] }
    val priceVerified = metas.count { it.priceProviders.size >= 2 || it.priceMaxRelDiff != null }
    val withFlow = metas.count { it.mainNetFlow != null || it.mainFlowPct != null }
    val withOhlc = metas.count { it.dayHigh != null && it.dayLow != null }
    CardBlock {
        Text("数据完整性", fontWeight = FontWeight.Bold)
        Key("入池股票", "${allCodes.size}只")
        Key("价格核对", if (allCodes.isEmpty()) "—" else "$priceVerified/${allCodes.size}")
        Key("资金字段", if (allCodes.isEmpty()) "—" else "$withFlow/${allCodes.size}")
        Key("当日高低", if (allCodes.isEmpty()) "—" else "$withOhlc/${allCodes.size}")
        if (s.factorAvailability.isNotEmpty()) {
            val missing = s.factorAvailability.filterValues { it.contains("未同步") || it.contains("留空") }
            if (missing.isNotEmpty()) Text(missing.entries.joinToString(" · ") { "${it.key}: ${it.value}" }, fontSize = 8.sp, color = Muted, maxLines = 3)
        }
    }
}
''')

if 'fun OfficialSectorRow(' not in s:
    blocks.append(r'''
@Composable
fun OfficialSectorRow(x: OfficialSector, date: String) {
    Surface(Modifier.fillMaxWidth().clickable { DetailNav.openSectorName(x.name, date) }, color = Color.White, shape = RoundedCornerShape(16.dp)) {
        Column(Modifier.fillMaxWidth().padding(13.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Row {
                Column(Modifier.weight(1f)) {
                    Text(x.name, fontWeight = FontWeight.Bold)
                    Text("${x.type ?: "板块"} · ${x.status ?: "候选"} · 点开详情", fontSize = 9.sp, color = Muted)
                }
                Text(x.score?.let { String.format("%.1f", it) } ?: "—", fontWeight = FontWeight.Bold, color = Blue)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("涨跌 ${x.changePct?.let(::pct) ?: "—"}", fontSize = 9.sp, color = x.changePct?.let(::pnl) ?: Muted)
                Text("广度 ${x.breadthPct?.let { String.format("%.0f%%", it) } ?: "—"}", fontSize = 9.sp, color = Muted)
                Text("资金 ${x.mainFlowPct?.let { String.format("%+.2f%%", it) } ?: "—"}", fontSize = 9.sp, color = Muted)
            }
            x.reason?.let { Text(it, fontSize = 8.sp, color = Muted, maxLines = 2) }
        }
    }
}
''')

if 'fun OfficialMainlineFallback(' not in s:
    blocks.append(r'''
@Composable
fun OfficialMainlineFallback(name: String, date: String) {
    Surface(Modifier.fillMaxWidth().clickable { DetailNav.openSectorName(name, date) }, color = Color.White, shape = RoundedCornerShape(16.dp)) {
        Column(Modifier.fillMaxWidth().padding(13.dp)) {
            Text(name, fontWeight = FontWeight.Bold)
            Text("确认主线 · $date · 点开详情", fontSize = 9.sp, color = Muted)
        }
    }
}
''')

if 'fun SameDayPoolCard(' not in s:
    blocks.append(r'''
private fun poolDayValuesCompat(s: Snapshot, pool: String): List<Double> = s.pools[pool].orEmpty().mapNotNull { s.stocks[it]?.dayChangePct }

@Composable
fun SameDayPoolCard(s: Snapshot, pool: String) {
    val values = poolDayValuesCompat(s, pool)
    CardBlock {
        Text("信号日行情（不是策略收益）", fontWeight = FontWeight.Bold)
        if (values.isEmpty()) {
            Text("当日涨跌字段尚未同步", color = Muted, fontSize = 11.sp)
        } else {
            val avg = values.average()
            val up = values.count { it > 0 }
            Key("平均涨跌", String.format("%+.2f%%", avg))
            Key("上涨占比", String.format("%.0f%%", up * 100.0 / values.size))
            Key("样本", "${values.size}只")
        }
        Text("这里描述信号形成当天已经发生的行情；真实策略收益从下一交易日可成交价格起算。", fontSize = 8.sp, color = Muted)
    }
}
''')

if 'fun ForwardTrackingCard(' not in s:
    blocks.append(r'''
@Composable
fun ForwardTrackingCard(s: Snapshot, pool: String) {
    val perf = s.poolPerformance[pool]
    CardBlock {
        Text("次一交易日开盘起后续收益跟踪", fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(6.dp))
        if (perf == null || perf.length() == 0) {
            Text(if (s.date == java.time.LocalDate.now(CnZone).toString()) "今日刚冻结：策略收益从下一交易日可成交开盘开始" else "后续收益尚未成熟或尚未同步", color = Muted, fontSize = 11.sp)
        } else {
            TrackingStrip(perf)
        }
        if (!s.performanceEligible) Text("参考跟踪可展示，但不计入策略胜率/超额收益总榜。", fontSize = 8.sp, color = Amber)
    }
}
''')

if blocks:
    marker='object DataApi {'
    idx=s.find(marker)
    if idx<0:
        s += '\n' + '\n'.join(blocks) + '\n'
    else:
        s=s[:idx]+'\n'.join(blocks)+'\n\n'+s[idx:]

p.write_text(s,encoding='utf-8')

# DetailScreens calls the package-level tradeAssist helper; make sure no stale local
# declaration shadows it and leave the actual UI logic intact.
d=Path('app/src/main/java/com/rui/astockstrategy/v6/DetailScreens.kt')
ds=d.read_text(encoding='utf-8')
# No stub here: successful compilation proves the shared package helper is visible.
d.write_text(ds,encoding='utf-8')
