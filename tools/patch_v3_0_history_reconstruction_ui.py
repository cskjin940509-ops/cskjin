from pathlib import Path

p = Path('app/src/main/java/com/rui/astockstrategy/v6/V29HistoryPatternLab.kt')
s = p.read_text(encoding='utf-8')

anchor = 'var horizonMode by remember { mutableStateOf("中短线") }'
if anchor not in s:
    raise SystemExit('v3.0 horizon selector state anchor missing')
s = s.replace(anchor, anchor + '\n    var sampleSourceMode by remember { mutableStateOf("真实样本") }', 1)

anchor = '    val d = data\n'
if anchor not in s:
    raise SystemExit('v3.0 history root anchor missing')
s = s.replace(anchor, '''    val rawHistory = data
    val reconstructionReady = rawHistory?.optJSONObject("reconstruction") != null
    val sourceChoices = if (reconstructionReady) listOf("真实样本", "历史重建") else listOf("真实样本")
    if (!reconstructionReady && sampleSourceMode == "历史重建") sampleSourceMode = "真实样本"
    val d = if (sampleSourceMode == "历史重建") rawHistory?.optJSONObject("reconstruction") else rawHistory
''', 1)

old = 'Text("真实冻结样本持续累积 · 每日重算 · 不删除失败案例", color = HMuted29, fontSize = 10.sp)'
new = '''Text(
                                if (sampleSourceMode == "历史重建") "行业板块周频历史重建 · 研究用 · 不计入样本外战绩"
                                else "真实冻结样本持续累积 · 每日重算 · 不删除失败案例",
                                color = HMuted29, fontSize = 10.sp
                            )'''
if old not in s:
    raise SystemExit('v3.0 subtitle anchor missing')
s = s.replace(old, new, 1)

old = '''        if (error != null) item { HNotice29(error!!, HAmber29) }
        item { HChoice29(listOf("中短线","中长线"), horizonMode) { horizonMode = it } }
        item { HChoice29(listOf("总览","路径","风险","条件"), tab) { tab = it } }'''
new = '''        if (error != null) item { HNotice29(error!!, HAmber29) }
        item { HSection29("样本来源") }
        item { HChoice29(sourceChoices, sampleSourceMode) { sampleSourceMode = it } }
        if (sampleSourceMode == "历史重建") item { ReconstructionNotice30(d) }
        else item { HNotice29("真实样本：只统计当时真实冻结并持续跟踪的正式样本，用于样本外验证。", HBlue29) }
        item { HChoice29(listOf("中短线","中长线"), horizonMode) { horizonMode = it } }
        item { HChoice29(listOf("总览","路径","风险","条件"), tab) { tab = it } }'''
if old not in s:
    raise SystemExit('v3.0 selector block missing')
s = s.replace(old, new, 1)

old = 'if (stages.isEmpty() && chase.isEmpty()) item { HNotice29("只有原始冻结快照真实记录主线阶段 / 追高风险后才参与统计；当前不会做代理补造。", HAmber29) }'
new = '''if (stages.isEmpty() && chase.isEmpty()) item {
                    HNotice29(
                        if (sampleSourceMode == "历史重建") "重建阶段 / 追高风险条件样本不足；重建标签由固定v3.0规则生成，不回写为当时真实标签。"
                        else "只有原始冻结快照真实记录主线阶段 / 追高风险后才参与统计；当前不会做代理补造。",
                        HAmber29
                    )
                }'''
if old not in s:
    raise SystemExit('v3.0 condition disclosure anchor missing')
s = s.replace(old, new, 1)

# Add a dedicated audit/coverage card. It deliberately makes reconstruction bias visible at the top of the page.
s += r'''

@Composable
private fun ReconstructionNotice30(d: JSONObject?) {
    val coverage = d?.optJSONObject("coverage")
    HCard29 {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("历史重建 · 独立研究口径", color = HAmber29, fontWeight = FontWeight.Bold, fontSize = 11.sp)
                Text("不是当时真实推荐，不计入真实样本数、真实收益或样本外可信度。", color = HMuted29, fontSize = 9.sp)
            }
            Text(d?.optString("version") ?: "—", color = HBlue29, fontSize = 8.sp)
        }
        HorizontalDivider()
        HKey29("历史跨度", "${coverage?.optString("startDate") ?: "—"} ～ ${coverage?.optString("endDate") ?: "—"}")
        HKey29("可用行业板块", (coverage?.optInt("boardsWithHistory") ?: 0).toString())
        HKey29("周频重建批次", (coverage?.optInt("weeklyCohorts") ?: 0).toString())
        HKey29("重建样本", (coverage?.optInt("samples") ?: 0).toString())
        HKey29("每周筛选", "Top ${coverage?.optInt("topNPerWeek") ?: 0}")
        HKey29("基准", coverage?.optString("benchmark") ?: "沪深300")
        Text("已知偏差：行业宇宙采用当前东方财富行业分类；历史主力资金和真实历史上涨扩散度缺失，因此未伪造这些因子。", color = HAmber29, fontSize = 8.sp)
        Text("概念板块暂不重建，避免把今天的概念分类穿越到过去。", color = HMuted29, fontSize = 8.sp)
    }
}
'''

# Version bump after the v2.9 patch chain has produced version 31 / 2.9.0.
g = Path('app/build.gradle.kts')
gs = g.read_text(encoding='utf-8')
gs = gs.replace('versionCode = 31', 'versionCode = 32')
gs = gs.replace('versionName = "2.9.0"', 'versionName = "3.0.0"')
if 'versionName = "3.0.0"' not in gs:
    raise SystemExit('v3.0 version bump failed')
g.write_text(gs, encoding='utf-8')

p.write_text(s, encoding='utf-8')
assert 'sampleSourceMode' in s
assert 'ReconstructionNotice30' in s
print('v3.0 separated history reconstruction UI integrated')
