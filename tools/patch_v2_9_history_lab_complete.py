from pathlib import Path

p = Path('app/src/main/java/com/rui/astockstrategy/v6/V29HistoryPatternLab.kt')
s = p.read_text(encoding='utf-8')

# Expand horizons.
s = s.replace(
    'return listOf("1D" to 1, "5D" to 5, "10D" to 10, "20D" to 20, "60D" to 60).map',
    'return listOf("1D" to 1, "2D" to 2, "3D" to 3, "5D" to 5, "10D" to 10, "20D" to 20, "40D" to 40, "60D" to 60, "120D" to 120, "250D" to 250).map',
)

# Add short/long horizon selector.
s = s.replace(
    'var tab by remember { mutableStateOf("总览") }',
    'var tab by remember { mutableStateOf("总览") }\n    var horizonMode by remember { mutableStateOf("中短线") }',
    1,
)

old = '''    val best = d?.optJSONObject("bestHolding")
    val trend = d?.optJSONObject("edgeTrend")
    val judge = trend?.optJSONObject("judgement")
    val hs = horizons29(d)
    val path = path29(d?.optJSONArray("eventPath"))
    val scatter = scatter29(d?.optJSONArray("riskScatter"))
    val conditions = d?.optJSONObject("conditions")'''
new = '''    val best = if (horizonMode == "中短线") d?.optJSONObject("bestHoldingShort") ?: d?.optJSONObject("bestHolding") else d?.optJSONObject("bestHoldingLong")
    val trend = d?.optJSONObject("edgeTrend")
    val judge = trend?.optJSONObject("judgement")
    val allHs = horizons29(d)
    val shortLabels = setOf("1D","2D","3D","5D","10D","20D")
    val longLabels = setOf("20D","40D","60D","120D","250D")
    val hs = allHs.filter { if (horizonMode == "中短线") it.label in shortLabels else it.label in longLabels }
    val path = path29(d?.optJSONArray("eventPath")).filter { it.day == 0 || if (horizonMode == "中短线") it.day <= 20 else it.day >= 20 }
    val scatter = scatter29(d?.optJSONArray("riskScatter"))
    val conditions = d?.optJSONObject("conditions")
    val bestText = if (horizonMode == "中短线") vitals?.optString("bestShortHoldingZh") ?: vitals?.optString("bestHoldingZh") else vitals?.optString("bestLongHoldingZh")'''
if old not in s:
    raise SystemExit('history state block not found')
s = s.replace(old, new, 1)

s = s.replace('HMetric29("最佳持有", vitals?.optString("bestHoldingZh") ?: "待样本"', 'HMetric29("最佳持有", bestText ?: "待样本"', 1)
s = s.replace('HKey29("当前最佳周期", vitals?.optString("bestHoldingZh") ?: "待样本")', 'HKey29("当前最佳周期", bestText ?: "待样本")', 1)

old = '''        if (error != null) item { HNotice29(error!!, HAmber29) }
        item { HChoice29(listOf("总览","路径","风险","条件"), tab) { tab = it } }'''
new = '''        if (error != null) item { HNotice29(error!!, HAmber29) }
        item { HChoice29(listOf("中短线","中长线"), horizonMode) { horizonMode = it } }
        item { HChoice29(listOf("总览","路径","风险","条件"), tab) { tab = it } }'''
if old not in s:
    raise SystemExit('history tab selector block not found')
s = s.replace(old, new, 1)

s = s.replace(
    '''                item { HSection29("历史优势变化") }
                item { EdgeTrend29(trend) }''',
    '''                item { HSection29("历史优势变化") }
                item { EdgeTrend29(trend) }
                item { HSection29("样本累计增长") }
                item { SampleGrowthChart29(d?.optJSONArray("sampleGrowth")) }''',
    1,
)
s = s.replace(
    '''                item { HSection29("路径区间") }
                item { PathRangeTable29(hs) }''',
    '''                item { HSection29("路径区间") }
                item { PathRangeTable29(hs) }
                item { HSection29("历史路径分型") }
                item { PathClustersCard29(d?.optJSONObject("pathClusters")) }''',
    1,
)

risk_anchor = '''                item {
                    HCard29 {
                        HKey29("历史中位最大有利涨幅", p29(d29(overall,"medianMFE")))
                        HKey29("历史中位最大不利跌幅", p29(d29(overall,"medianMAE")))
                        HKey29("历史中位最大回撤", p29(d29(overall,"medianMaxDrawdown")))
                    }
                }'''
risk_new = risk_anchor + '''
                item { HSection29("未来收益分布") }
                item {
                    val target = if (horizonMode == "中短线") "5D" else "60D"
                    ReturnDistribution29(d?.optJSONObject("returnDistributions")?.optJSONObject(target), target)
                }
                item { HSection29("成功 / 失败样本对比") }
                item { SuccessFailureCard29(d?.optJSONObject("successFailure")) }
                item { HSection29("典型历史案例") }
                item { HistoryExamplesCard29(d?.optJSONObject("successFailure")) }'''
if risk_anchor not in s:
    raise SystemExit('risk block not found')
s = s.replace(risk_anchor, risk_new, 1)

cond_anchor = '''                if (stages.isEmpty() && chase.isEmpty()) item { HNotice29("只有原始冻结快照真实记录主线阶段 / 追高风险后才参与统计；当前不会做代理补造。", HAmber29) }
                else {
                    items(stages) { ConditionRow29(it) }
                    items(chase) { ConditionRow29(it) }
                }'''
cond_new = cond_anchor + '''
                item { StageChaseHeat29(conditions?.optJSONArray("stageByChase")) }'''
if cond_anchor not in s:
    raise SystemExit('condition block not found')
s = s.replace(cond_anchor, cond_new, 1)

# Append additional composables directly to the generated Kotlin source.
s += r'''

@Composable
private fun SampleGrowthChart29(a: JSONArray?) {
    HCard29 {
        if (a == null || a.length() == 0) {
            Text("尚无累计样本", color = HMuted29, fontSize = 10.sp)
            return@HCard29
        }
        val values = (0 until a.length()).map { i -> a.optJSONObject(i)?.optInt("cumulativeSamples") ?: 0 }
        val maxV = (values.maxOrNull() ?: 1).coerceAtLeast(1)
        Canvas(Modifier.fillMaxWidth().height(130.dp)) {
            if (values.size == 1) {
                drawCircle(HBlue29, 6f, Offset(size.width / 2f, size.height / 2f))
            } else {
                val graph = Path()
                values.forEachIndexed { i, v ->
                    val x = i.toFloat() / (values.size - 1).toFloat() * size.width
                    val y = size.height - (v.toFloat() / maxV.toFloat() * size.height * 0.85f) - size.height * 0.05f
                    if (i == 0) graph.moveTo(x, y) else graph.lineTo(x, y)
                }
                drawPath(graph, HBlue29, style = androidx.compose.ui.graphics.drawscope.Stroke(width = 3f))
            }
        }
        val first = a.optJSONObject(0)
        val last = a.optJSONObject(a.length() - 1)
        Row {
            Text(first?.optString("date") ?: "—", Modifier.weight(1f), color = HMuted29, fontSize = 8.sp)
            Text("累计 ${last?.optInt("cumulativeSamples") ?: 0} 个样本", fontWeight = FontWeight.Bold, fontSize = 9.sp)
        }
    }
}

@Composable
private fun PathClustersCard29(o: JSONObject?) {
    HCard29 {
        val n = o?.optInt("matureSamples") ?: 0
        val a = o?.optJSONArray("clusters")
        if (n == 0 || a == null || a.length() == 0) {
            Text("5日路径尚未成熟，暂不进行路径分型。", color = HMuted29, fontSize = 10.sp)
        } else {
            for (i in 0 until a.length()) {
                val x = a.optJSONObject(i) ?: continue
                Row {
                    Text(x.optString("name"), Modifier.weight(1f), fontWeight = FontWeight.Bold, fontSize = 10.sp)
                    Text("${x.optInt("sampleCount")}例 · ${p29(d29(x,"share"))}", Modifier.width(92.dp), fontSize = 9.sp)
                    Text(p29(d29(x,"medianFiveDayReturn")), color = c29(d29(x,"medianFiveDayReturn")), fontSize = 10.sp)
                }
            }
            Text(o.optString("methodZh"), color = HMuted29, fontSize = 8.sp)
        }
    }
}

@Composable
private fun ReturnDistribution29(o: JSONObject?, label: String) {
    HCard29 {
        val n = o?.optInt("members") ?: 0
        val a = o?.optJSONArray("bins")
        if (n == 0 || a == null) {
            Text("$label 收益分布尚未成熟。", color = HMuted29, fontSize = 10.sp)
            return@HCard29
        }
        Text("$label 成熟样本 $n", fontWeight = FontWeight.Bold, fontSize = 10.sp)
        for (i in 0 until a.length()) {
            val x = a.optJSONObject(i) ?: continue
            val share = d29(x, "share") ?: 0.0
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(x.optString("label"), Modifier.width(58.dp), color = HMuted29, fontSize = 8.sp)
                LinearProgressIndicator(progress = { share.toFloat().coerceIn(0f, 1f) }, modifier = Modifier.weight(1f).height(6.dp))
                Spacer(Modifier.width(6.dp))
                Text("${x.optInt("count")} · ${p29(share)}", Modifier.width(68.dp), fontSize = 8.sp)
            }
        }
    }
}

@Composable
private fun SuccessFailureCard29(o: JSONObject?) {
    HCard29 {
        val mature = o?.optInt("matureFiveDaySamples") ?: 0
        val success = o?.optJSONObject("success")
        val failure = o?.optJSONObject("failure")
        if (mature == 0) {
            Text("5日样本尚未成熟，成功/失败对比将在样本自然成熟后出现。", color = HMuted29, fontSize = 10.sp)
            return@HCard29
        }
        Text(o.optString("definitionZh"), color = HMuted29, fontSize = 8.sp)
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Column(Modifier.weight(1f)) {
                Text("成功样本", color = HRed29, fontWeight = FontWeight.Bold, fontSize = 10.sp)
                HKey29("数量", (success?.optInt("sampleCount") ?: 0).toString())
                HKey29("平均评分", n29(d29(success,"averageScore")))
                HKey29("平均吸筹", n29(d29(success,"averageAccumulation")))
                HKey29("高追高占比", p29(d29(success,"highChaseRatio")))
                HKey29("中位MAE", p29(d29(success,"medianMAE")))
            }
            Column(Modifier.weight(1f)) {
                Text("失败样本", color = HGreen29, fontWeight = FontWeight.Bold, fontSize = 10.sp)
                HKey29("数量", (failure?.optInt("sampleCount") ?: 0).toString())
                HKey29("平均评分", n29(d29(failure,"averageScore")))
                HKey29("平均吸筹", n29(d29(failure,"averageAccumulation")))
                HKey29("高追高占比", p29(d29(failure,"highChaseRatio")))
                HKey29("中位MAE", p29(d29(failure,"medianMAE")))
            }
        }
    }
}

@Composable
private fun HistoryExamplesCard29(o: JSONObject?) {
    HCard29 {
        val top = o?.optJSONArray("topExamples")
        val bottom = o?.optJSONArray("bottomExamples")
        if ((top == null || top.length() == 0) && (bottom == null || bottom.length() == 0)) {
            Text("5日成熟案例不足。", color = HMuted29, fontSize = 10.sp)
            return@HCard29
        }
        Text("典型成功案例", color = HRed29, fontWeight = FontWeight.Bold, fontSize = 10.sp)
        if (top != null) {
            for (i in 0 until minOf(3, top.length())) {
                val x = top.optJSONObject(i) ?: continue
                Row {
                    Text("${x.optString("name")} ${x.optString("code")}", Modifier.weight(1f), fontSize = 9.sp)
                    Text(p29(d29(x,"fiveDayReturn")), color = c29(d29(x,"fiveDayReturn")), fontSize = 9.sp)
                }
            }
        }
        HorizontalDivider()
        Text("典型失败案例", color = HGreen29, fontWeight = FontWeight.Bold, fontSize = 10.sp)
        if (bottom != null) {
            for (i in 0 until minOf(3, bottom.length())) {
                val x = bottom.optJSONObject(i) ?: continue
                Row {
                    Text("${x.optString("name")} ${x.optString("code")}", Modifier.weight(1f), fontSize = 9.sp)
                    Text(p29(d29(x,"fiveDayReturn")), color = c29(d29(x,"fiveDayReturn")), fontSize = 9.sp)
                }
            }
        }
    }
}

@Composable
private fun StageChaseHeat29(a: JSONArray?) {
    HCard29 {
        if (a == null || a.length() == 0) {
            Text("主线阶段 × 追高风险交叉样本尚不足。", color = HMuted29, fontSize = 10.sp)
            return@HCard29
        }
        Text("主线阶段 × 追高风险条件单元", fontWeight = FontWeight.Bold, fontSize = 10.sp)
        for (i in 0 until a.length()) {
            val x = a.optJSONObject(i) ?: continue
            val alpha = d29(x, "fiveDayMedianAlpha")
            val bg = when {
                alpha == null -> Color(0xFFF3F5F9)
                alpha >= 0.02 -> Color(0xFFFFE7E3)
                alpha > 0 -> Color(0xFFFFF2EF)
                alpha <= -0.02 -> Color(0xFFE2F4EC)
                else -> Color(0xFFEEF8F4)
            }
            Surface(color = bg, shape = RoundedCornerShape(9.dp)) {
                Row(Modifier.fillMaxWidth().padding(8.dp)) {
                    Text("${x.optString("mainlineState")} · ${x.optString("chaseRisk")}", Modifier.weight(1f), fontSize = 9.sp)
                    Text("N=${x.optInt("fiveDayMembers")}", Modifier.width(42.dp), color = HMuted29, fontSize = 8.sp)
                    Text(p29(alpha), color = c29(alpha), fontWeight = FontWeight.Bold, fontSize = 9.sp)
                }
            }
        }
    }
}
'''

p.write_text(s, encoding='utf-8')
print('v2.9 history lab complete UI integrated')
