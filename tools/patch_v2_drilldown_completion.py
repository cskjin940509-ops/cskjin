from pathlib import Path
import re

# This patch intentionally runs after patch_v1_9_data_display.py and
# patch_audit_tracking_labels.py. Keep it small: only close the remaining
# drill-down gaps instead of rewriting the already-tested v1.9 data contract.

# ---------------------------------------------------------------------------
# TailDecision: parse full sector objects and make confirmed/candidate sectors
# clickable into the normal SectorDetailScreen.
# ---------------------------------------------------------------------------
t = Path('app/src/main/java/com/rui/astockstrategy/v6/TailDecision.kt')
s = t.read_text(encoding='utf-8')

if 'data class TailSectorDetail(' not in s:
    marker = 'data class TailDecision(\n'
    block = '''data class TailSectorDetail(
    val boardCode: String,
    val name: String,
    val type: String,
    val score: Double?,
    val status: String,
    val changePct: Double?,
    val amount: Double?,
    val mainNetFlow: Double?,
    val mainFlowPct: Double?,
    val breadthPct: Double?,
    val rs20: Double?,
    val rs60: Double?,
    val mta: String?,
    val confidence: String?,
    val reason: String?
)

'''
    if marker not in s:
        raise SystemExit('TailDecision model marker not found')
    s = s.replace(marker, block + marker, 1)

# Extend TailDecision model.
old = '''    val confirmedMainlines: List<String>,
    val candidateMainlines: List<String>,
    val pools: Map<String, List<String>>,'''
new = '''    val confirmedMainlines: List<String>,
    val candidateMainlines: List<String>,
    val confirmedSectorDetails: List<TailSectorDetail>,
    val candidateSectorDetails: List<TailSectorDetail>,
    val pools: Map<String, List<String>>,'''
if old in s:
    s = s.replace(old, new, 1)
elif 'val confirmedSectorDetails:' not in s:
    raise SystemExit('unexpected TailDecision model shape')

# Insert clickable sector cards after the Tail status card and before noTrade.
needle = '''        if (current.noTrade) {'''
insert = '''        val tailSectors = if (current.confirmedSectorDetails.isNotEmpty()) current.confirmedSectorDetails else current.candidateSectorDetails
        if (tailSectors.isNotEmpty()) {
            Text(
                if (current.confirmedSectorDetails.isNotEmpty()) "尾盘确认主线详情" else "尾盘候选板块详情",
                fontWeight = FontWeight.Bold,
                fontSize = 14.sp
            )
            tailSectors.take(6).forEach { sector -> TailSectorDetailRow(sector, current.date) }
        }

        if (current.noTrade) {'''
if 'TailSectorDetailRow(sector, current.date)' not in s:
    if needle not in s:
        raise SystemExit('Tail noTrade marker not found')
    s = s.replace(needle, insert, 1)

# Parser helper inside parseTail.
parser_marker = '''    fun number(x: JSONObject, k: String): Double? = if (!x.has(k) || x.isNull(k)) null else runCatching { x.getDouble(k) }.getOrNull()
'''
parser_helper = '''    fun sectorDetails(a: org.json.JSONArray?): List<TailSectorDetail> = if (a == null) emptyList() else (0 until a.length()).mapNotNull { i ->
        val x = a.optJSONObject(i) ?: return@mapNotNull null
        val name = x.optString("name")
        if (name.isBlank()) return@mapNotNull null
        TailSectorDetail(
            boardCode = x.optString("boardCode"),
            name = name,
            type = x.optString("type", "板块"),
            score = number(x, "score"),
            status = x.optString("status", "观察"),
            changePct = number(x, "changePct"),
            amount = number(x, "amount"),
            mainNetFlow = number(x, "mainNetFlow"),
            mainFlowPct = number(x, "mainFlowPct"),
            breadthPct = number(x, "breadthPct"),
            rs20 = number(x, "RS20"),
            rs60 = number(x, "RS60"),
            mta = x.optString("MTA").takeIf { it.isNotBlank() },
            confidence = x.optString("confidence").takeIf { it.isNotBlank() },
            reason = x.optString("reason").takeIf { it.isNotBlank() }
        )
    }
'''
if 'fun sectorDetails(' not in s:
    if parser_marker not in s:
        raise SystemExit('Tail parser marker not found')
    s = s.replace(parser_marker, parser_marker + parser_helper, 1)

# Construct the two rich arrays from the same JSON arrays already used for names.
old = '''        confirmedMainlines = names(o.optJSONArray("confirmedMainlines")),
        candidateMainlines = names(o.optJSONArray("candidateMainlines")),
        pools = pools,'''
new = '''        confirmedMainlines = names(o.optJSONArray("confirmedMainlines")),
        candidateMainlines = names(o.optJSONArray("candidateMainlines")),
        confirmedSectorDetails = sectorDetails(o.optJSONArray("confirmedMainlines")),
        candidateSectorDetails = sectorDetails(o.optJSONArray("candidateMainlines")),
        pools = pools,'''
if old in s:
    s = s.replace(old, new, 1)
elif 'confirmedSectorDetails = sectorDetails' not in s:
    raise SystemExit('TailDecision constructor marker not found')

# Clickable sector card, inserted before MiniMetric.
marker = '''@Composable
private fun MiniMetric(label: String, value: String, modifier: Modifier) {'''
helper = '''@Composable
private fun TailSectorDetailRow(x: TailSectorDetail, date: String) {
    val breadth = x.breadthPct?.coerceIn(0.0, 100.0)
    val up = breadth?.toInt() ?: 0
    val down = if (breadth != null) 100 - up else 0
    val board = Board(
        code = x.boardCode,
        name = x.name,
        change = x.changePct,
        amount = x.amount,
        flow = x.mainNetFlow,
        flowPct = x.mainFlowPct,
        up = up,
        down = down,
        flat = 0,
        type = if (x.type == "概念") "concept" else "industry"
    )
    Card(
        Modifier.fillMaxWidth().clickable { DetailNav.openSector(board, date) },
        shape = RoundedCornerShape(14.dp)
    ) {
        Column(Modifier.fillMaxWidth().padding(11.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.Top) {
                Column(Modifier.weight(1f)) {
                    Text(x.name, fontWeight = FontWeight.Bold)
                    Text("${x.status} · ${x.type} · 点开查看趋势/资金/成分股", fontSize = 9.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Text(x.score?.let { String.format("%.1f", it) } ?: "—", fontWeight = FontWeight.Bold)
            }
            Text(
                "涨跌 ${x.changePct?.let { String.format("%+.2f%%", it) } ?: "—"} · " +
                    "主力占比 ${x.mainFlowPct?.let { String.format("%+.2f%%", it) } ?: "—"} · " +
                    "广度 ${x.breadthPct?.let { String.format("%.0f%%", it) } ?: "—"}",
                fontSize = 9.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Text("${x.mta ?: "趋势待同步"} · 置信度 ${x.confidence ?: "—"}", fontSize = 8.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

'''
if 'private fun TailSectorDetailRow' not in s:
    if marker not in s:
        raise SystemExit('MiniMetric marker not found')
    s = s.replace(marker, helper + marker, 1)

t.write_text(s, encoding='utf-8')

# ---------------------------------------------------------------------------
# SectorDetailScreen: Snapshot already contains sectorPerformance, but the
# detail page did not display it. Add the exact same Forward Tracking semantics
# as stock/pool pages: next tradable open, reference-only label when applicable.
# ---------------------------------------------------------------------------
d = Path('app/src/main/java/com/rui/astockstrategy/v6/DetailScreens.kt')
ds = d.read_text(encoding='utf-8')

state_marker = '''    val state = f?.status ?: if (isFrozenMainline) "正式主线" else "板块观察"
'''
if 'val sectorPerf = snapshot?.sectorPerformance?.get(ref.name)' not in ds:
    if state_marker not in ds:
        raise SystemExit('Sector state marker not found')
    ds = ds.replace(state_marker, state_marker + '    val sectorPerf = snapshot?.sectorPerformance?.get(ref.name)\n', 1)

members_marker = '''            item { DetailSectionTitle("成分股") }'''
tracking_block = '''            item { DetailSectionTitle("策略后续跟踪") }
            item {
                DetailCard {
                    Text("从正式信号后的下一交易日可成交开盘起算，不把信号日涨幅计入策略收益。", color = DetailMuted, fontSize = 9.sp)
                    Spacer(Modifier.height(7.dp))
                    if (sectorPerf == null || sectorPerf.length() == 0) {
                        Text("当前尚未成熟 / 尚未同步", color = DetailMuted, fontSize = 10.sp)
                    } else {
                        TrackingStrip(sectorPerf)
                        Spacer(Modifier.height(6.dp))
                        DetailKey("当前 Tracking", detailValue(sectorPerf, "current"))
                        DetailKey("MFE", detailValue(sectorPerf, "MFE"))
                        DetailKey("MAE", detailValue(sectorPerf, "MAE"))
                        if (snapshot != null && !snapshot.performanceEligible) {
                            Text("参考 Tracking · 该批次不进入胜率、Alpha或因子成绩统计。", color = DetailMuted, fontSize = 9.sp)
                        }
                    }
                }
            }
            item { DetailSectionTitle("成分股") }'''
if 'DetailSectionTitle("策略后续跟踪")' not in ds:
    if members_marker not in ds:
        raise SystemExit('Sector members marker not found')
    ds = ds.replace(members_marker, tracking_block, 1)

d.write_text(ds, encoding='utf-8')

# v2.0 follows v1.9 generated by patch_v1_9_data_display.py.
g = Path('app/build.gradle.kts')
gs = g.read_text(encoding='utf-8')
gs = gs.replace('versionCode = 20', 'versionCode = 21')
gs = gs.replace('versionName = "1.9.0"', 'versionName = "2.0.0"')
g.write_text(gs, encoding='utf-8')
