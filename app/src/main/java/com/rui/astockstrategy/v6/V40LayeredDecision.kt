package com.rui.astockstrategy.v6

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

private const val RADAR40_PATH = "astock_radar/latest.json"

private val V40Blue = Color(0xFF3155D6)
private val V40Ink = Color(0xFF171A22)
private val V40Muted = Color(0xFF747B8D)
private val V40Red = Color(0xFFD84343)
private val V40Green = Color(0xFF15966A)
private val V40Amber = Color(0xFFAE6A00)
private val V40SoftBlue = Color(0xFFE9EDFF)
private val V40SoftGreen = Color(0xFFE8F6F0)
private val V40SoftAmber = Color(0xFFFFF1E7)
private val V40SoftGray = Color(0xFFF3F5F9)

data class LayerSector40(
    val code: String,
    val name: String,
    val type: String,
    val stage: String,
    val formation: Double?,
    val accumulation: Double?,
    val extensionPenalty: Double?,
    val chaseRisk: String,
    val changePct: Double?,
    val flowPct: Double?,
    val breadthPct: Double?,
    val rs20: Double?,
    val rs60: Double?,
    val mta: String,
    val reason: String
)

data class LayerStock40(
    val code: String,
    val name: String,
    val sector: String,
    val stage: String,
    val action: String,
    val changePct: Double?,
    val amount: Double?,
    val turnover: Double?,
    val volumeRatio: Double?,
    val baseEvidence: Double?,
    val marginEvidence: Double?,
    val etfEvidence: Double?,
    val flowEvidence: Double?,
    val mainFlowPct: Double?,
    val chaseRisk: String,
    val reason: String
) {
    val evidenceCount: Int
        get() = listOf(baseEvidence, marginEvidence, etfEvidence, flowEvidence).count { it != null }
}

data class LayerRadar40(
    val date: String,
    val capturedAt: String,
    val status: String,
    val strategyVersion: String,
    val dataSource: String,
    val factorAvailability: Map<String, String>,
    val slowDataDate: String,
    val slowState: String,
    val sectors: List<LayerSector40>,
    val stocks: List<LayerStock40>
)

/**
 * v4.3 does not create a new score. It turns the persisted cloud feeds into an
 * auditable four-layer decision chain and explicitly blocks real execution
 * while the market-level risk budget is not yet validated out of sample.
 */
@Composable
fun LayeredDecisionHome40(
    snapshot: Snapshot?,
    preview: List<PreviewSector>,
    quotes: Map<String, Quote>
) {
    var radar by remember { mutableStateOf<LayerRadar40?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        while (true) {
            runCatching { fetchLayerRadar40() }
                .onSuccess { radar = it; error = null }
                .onFailure { error = it.javaClass.simpleName }
            delay(30_000)
        }
    }

    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        FrameworkHeader40(radar, error)
        DecisionChain40(snapshot, radar)
        MarketLayer40(snapshot, quotes)

        val sectors = radar?.sectors.orEmpty()
        SectorLayer40(sectors, preview, radar?.date)

        // The server has already applied sector membership and stage gates.
        // The client only orders rows for display; opening the app never recomputes a pool.
        val candidates = radar?.stocks.orEmpty()
            .sortedWith(
                compareByDescending<LayerStock40> { it.evidenceCount }
                    .thenBy { chaseOrder40(it.chaseRisk) }
                    .thenByDescending { it.turnover ?: -1.0 }
            )
        StockLayer40(candidates, radar?.date)
        ExecutionBoundary40(snapshot, sectors, candidates)
        DataTruthCard40(snapshot, radar)
    }
}

@Composable
private fun FrameworkHeader40(data: LayerRadar40?, error: String?) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color(0xFF1E2A52)),
        shape = RoundedCornerShape(20.dp)
    ) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("分层决策 v4.3", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 20.sp)
                    Text("市场 → 板块 → 个股 → 执行", color = Color(0xFFD7DFFF), fontSize = 11.sp)
                }
                Surface(color = if (data != null) Color(0xFF295E53) else Color(0xFF6A4A1E), shape = RoundedCornerShape(20.dp)) {
                    Text(
                        if (data != null) "雷达已连接" else "读取中",
                        color = Color.White,
                        fontSize = 9.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(horizontal = 9.dp, vertical = 5.dp)
                    )
                }
            }
            Text(
                "目标是提前发现价格尚未充分反映的潜在主线；所有旧评分只保留为研究证据，不直接生成买入结论。",
                color = Color(0xFFE8ECFF),
                fontSize = 10.sp
            )
            Text(
                data?.let { "${it.date} · ${stageStatusZh40(it.status)} · ${shortTime40(it.capturedAt)}" }
                    ?: error?.let { "云端雷达暂不可用：$it" }
                    ?: "正在读取云端雷达…",
                color = Color(0xFFBAC6F8),
                fontSize = 9.sp
            )
        }
    }
}

@Composable
private fun DecisionChain40(snapshot: Snapshot?, radar: LayerRadar40?) {
    LayerCard40("决策链总览", "后一级必须服从前一级，不能由个股高分反推板块或市场") {
        ChainRow40("1", "市场风险预算", "研究中", V40Amber)
        ChainDivider40()
        ChainRow40(
            "2",
            "潜在主线板块",
            radar?.sectors?.count { it.stage in setOf("RADAR", "EMERGING", "CONFIRMING") }
                ?.let { "$it 个在跟踪" } ?: "等待数据",
            if (radar != null) V40Blue else V40Muted
        )
        ChainDivider40()
        ChainRow40("3", "板块内个股", "只从允许板块筛选", V40Blue)
        ChainDivider40()
        ChainRow40(
            "4",
            "买卖与仓位",
            if (snapshot?.performanceEligible == true) "仅影子组合" else "审计未通过",
            V40Amber
        )
    }
}

@Composable
private fun MarketLayer40(snapshot: Snapshot?, quotes: Map<String, Quote>) {
    LayerCard40("第一层｜市场", "决定能不能做、最多做多少；当前不硬算未经验证的仓位") {
        val indices = listOf("sh000001", "sz399006", "sh000300", "sh000852")
        val validChanges = indices.mapNotNull { quotes[it]?.change }
        val positive = validChanges.count { it > 0 }
        KeyRow40("当前环境（旧模型参考）", snapshot?.let { displayRegimeZh27(it.regime) } ?: "未同步")
        KeyRow40("主要指数广度", if (validChanges.isEmpty()) "未同步" else "$positive/${validChanges.size} 上涨")
        Spacer(Modifier.height(4.dp))
        EvidenceStatus40("赚钱效应", "底层市场广度待接入历史分位", "研究中")
        EvidenceStatus40("两融情绪", "原始T+1数据已接；市场层阈值未冻结", "待验证")
        EvidenceStatus40("ETF资金强弱", "份额变化口径已接；托底/进攻结构待区分", "待验证")
        EvidenceStatus40("综合资金情绪", "仅保留研究标签，不沿用漂移权重", "不生产")
        Notice40("市场风险预算尚未完成滚动样本外验证，因此 v4.3 不显示伪精确仓位百分比，也不授权真实自动交易。")
    }
}

@Composable
private fun SectorLayer40(
    sectors: List<LayerSector40>,
    preview: List<PreviewSector>,
    date: String?
) {
    LayerCard40("第二层｜板块", "寻找资金先行、价格未大涨的形成过程；状态机不是单一分数") {
        if (sectors.isEmpty()) {
            Text(
                if (preview.isEmpty()) "等待板块雷达数据" else "正式雷达未同步；盘中基础候选 ${preview.size} 个",
                color = V40Muted,
                fontSize = 10.sp
            )
        } else {
            val stageCounts = sectors.groupingBy { stageZh40(it.stage) }.eachCount()
            Text(
                stageCounts.entries.joinToString(" · ") { "${it.key}${it.value}" },
                color = V40Muted,
                fontSize = 9.sp
            )
            Spacer(Modifier.height(3.dp))
            sectors.sortedWith(compareBy({ stageOrder40(it.stage) }, { chaseOrder40(it.chaseRisk) }))
                .take(6)
                .forEachIndexed { index, sector ->
                    SectorEvidenceRow40(sector, date)
                    if (index < minOf(5, sectors.lastIndex)) HorizontalDivider(color = Color(0xFFF0F1F4))
                }
        }
        Notice40("当前板块雷达已有价格、成交、广度和主力资金证据；板块级两融净流入强度、加速度、扩散率、拥挤度仍需后端按历史成分聚合后再参与判断。")
    }
}

@Composable
private fun SectorEvidenceRow40(sector: LayerSector40, date: String?) {
    val preferred = sector.stage in setOf("RADAR", "EMERGING", "CONFIRMING") &&
        sector.chaseRisk != "HIGH" && (sector.changePct ?: 0.0) < 4.0
    Column(
        Modifier.fillMaxWidth().clickable { DetailNav.openSectorName(sector.name, date) }.padding(vertical = 7.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("${sector.name} · ${sector.type}", color = V40Ink, fontWeight = FontWeight.SemiBold, fontSize = 12.sp)
                Text(
                    "${stageZh40(sector.stage)} · 涨跌 ${pct40(sector.changePct)} · 扩散 ${plainPct40(sector.breadthPct)}",
                    color = V40Muted,
                    fontSize = 9.sp
                )
            }
            StatusPill40(
                if (preferred) "优先研究" else chaseZh40(sector.chaseRisk),
                if (preferred) V40Green else stageColor40(sector.stage)
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(5.dp)) {
            EvidenceChip40("B0 行情", sector.breadthPct != null)
            EvidenceChip40("B1 两融", false)
            EvidenceChip40("B2 ETF", false)
            EvidenceChip40("B3 主力", sector.flowPct != null)
        }
        Text(
            "主力 ${pct40(sector.flowPct)} · RS20 ${number40(sector.rs20)} · 价格延伸扣分 ${number40(sector.extensionPenalty)}",
            color = V40Muted,
            fontSize = 8.sp
        )
    }
}

@Composable
private fun StockLayer40(stocks: List<LayerStock40>, date: String?) {
    LayerCard40("第三层｜个股", "只在允许板块内看成交结构与资金证据；不再全市场按总分取前几名") {
        if (stocks.isEmpty()) {
            Text("当前没有满足板块服从关系的个股观察项", color = V40Muted, fontSize = 10.sp)
        } else {
            stocks.take(8).forEachIndexed { index, stock ->
                Column(
                    Modifier.fillMaxWidth().clickable { DetailNav.openStock(stock.code, date) }.padding(vertical = 7.dp),
                    verticalArrangement = Arrangement.spacedBy(3.dp)
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("${stock.name} ${stock.code}", fontWeight = FontWeight.SemiBold, fontSize = 11.sp)
                            Text("${stock.sector} · ${stageZh40(stock.stage)}", color = V40Muted, fontSize = 8.sp)
                        }
                        StatusPill40("${stock.evidenceCount}/4类证据", if (stock.evidenceCount >= 3) V40Green else V40Blue)
                    }
                    Text(
                        "涨跌 ${pct40(stock.changePct)} · 成交额 ${amount40(stock.amount)} · 换手 ${plainPct40(stock.turnover)} · 量比 ${number40(stock.volumeRatio)}",
                        color = V40Muted,
                        fontSize = 8.sp
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                        EvidenceChip40("B0", stock.baseEvidence != null)
                        EvidenceChip40("B1", stock.marginEvidence != null)
                        EvidenceChip40("B2", stock.etfEvidence != null)
                        EvidenceChip40("B3", stock.flowEvidence != null || stock.mainFlowPct != null)
                    }
                    Text("${stock.action} · 追高${chaseZh40(stock.chaseRisk)}", color = if (stock.chaseRisk == "HIGH") V40Amber else V40Muted, fontSize = 8.sp)
                }
                if (index < minOf(7, stocks.lastIndex)) HorizontalDivider(color = Color(0xFFF0F1F4))
            }
        }
        Notice40("成交量是个股层已确认的核心研究方向；若量比/历史成交基准显示“—”，表示后端尚未提供，v4.3 不用当天成交额冒充已验证的放量信号。")
    }
}

@Composable
private fun ExecutionBoundary40(
    snapshot: Snapshot?,
    sectors: List<LayerSector40>,
    stocks: List<LayerStock40>
) {
    LayerCard40("第四层｜执行", "只有市场、板块、个股三层依次成立后，才允许讨论买卖") {
        GateRow40("市场允许风险", false, "仓位模型尚未样本外冻结")
        GateRow40("板块具备早期证据", sectors.any { it.stage in setOf("RADAR", "EMERGING", "CONFIRMING") }, "状态机持续跟踪")
        GateRow40("个股成交结构可核验", stocks.any { it.volumeRatio != null }, "缺失时不补假信号")
        GateRow40("快照可用于后续跟踪", snapshot?.performanceEligible == true, snapshot?.let(::snapshotAuditLabel) ?: "未同步")
        Surface(color = V40SoftAmber, shape = RoundedCornerShape(12.dp)) {
            Column(Modifier.fillMaxWidth().padding(10.dp)) {
                Text("当前许可：研究观察 / 影子组合", color = V40Amber, fontWeight = FontWeight.Bold, fontSize = 11.sp)
                Text("不连接券商、不自动下单；旧版执行面板仅保留为模拟记录。", color = V40Muted, fontSize = 9.sp)
            }
        }
    }
}

@Composable
private fun DataTruthCard40(snapshot: Snapshot?, radar: LayerRadar40?) {
    LayerCard40("数据与时点", "任何影响结论的数据都必须能回答：何时发生、何时可得、来自哪里") {
        KeyRow40("盘中行情", "T+0 · 只作实时事实")
        KeyRow40("两融 / ETF份额", radar?.slowDataDate?.let { "T+1 · 数据日 $it" } ?: "T+1 · 未同步")
        KeyRow40("雷达时点", radar?.capturedAt?.ifBlank { "—" } ?: "—")
        KeyRow40("策略版本", radar?.strategyVersion?.ifBlank { "—" } ?: "—")
        KeyRow40("正式快照", snapshot?.let { "${it.date} · ${snapshotAuditLabel(it)}" } ?: "未同步")
        Text(
            "硬约束：不使用未来数据；不把当前行业成员倒套历史；ETF估算资金与真实一级申赎分开；缺失值不补成中性分。",
            color = V40Muted,
            fontSize = 8.sp
        )
    }
}

@Composable
fun FrameworkResearchScreen40(snapshot: Snapshot?) {
    var evidence by remember { mutableStateOf<JSONObject?>(null) }
    var evidenceError by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) {
        while (true) {
            runCatching {
                withContext(Dispatchers.IO) { JSONObject(BackendClient.fetchText("astock_ai_portfolio/latest.json")) }
            }.onSuccess { evidence = it; evidenceError = null }
                .onFailure { evidence = null; evidenceError = "验证报告读取失败，不能确认审核状态" }
            delay(30_000)
        }
    }
    LazyColumn(contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF1E2A52)), shape = RoundedCornerShape(18.dp)) {
                Column(Modifier.fillMaxWidth().padding(15.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("策略验证与证据进度", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 18.sp)
                    Text("先验证领先性，再冻结公式；研究结果不能反写历史样本。", color = Color(0xFFD7DFFF), fontSize = 10.sp)
                }
            }
        }
        evidenceError?.let { message -> item { Text(message, color = V40Amber) } }
        item { StrategyResearch46(evidence) }
        item {
            LayerCard40("待检验变量", "窗口由数据决定，不预设“看起来合理”的固定参数") {
                KeyRow40("市场层", "赚钱效应、全市场两融、宽基ETF、美股、中美长债")
                KeyRow40("板块层", "ETF流、两融净流入/加速度/扩散/拥挤、价格与广度")
                KeyRow40("个股层", "成交量、成交额、换手、板块内相对强弱、个股两融")
                KeyRow40("候选窗口", "1/3/5/7/10/20/30/60/120/250日")
                KeyRow40("未来结果", "收益、超额、胜率、最大上涨、最大回撤、趋势持续")
            }
        }
        item {
            LayerCard40("B0–B123 的新定位", "证据分类与增量贡献分析，不是最高分买入规则") {
                KeyRow40("B0", "行情、成交、广度等基础证据")
                KeyRow40("B1 / B2 / B3", "两融 / ETF / 主力资金证据")
                KeyRow40("B12 / B13 / B23", "两类资金交叉确认")
                KeyRow40("B123", "三类资金共同确认")
                KeyRow40("旧 B4", "兼容展示；不再作为最终买入结论")
            }
        }
        item {
            LayerCard40("进入生产的门槛", "任何一项不满足，就继续留在研究层") {
                listOf(
                    "无前视偏差且时点可复现",
                    "训练期、验证期与最终测试期严格分离",
                    "Walk-forward 在不同市场环境下稳定",
                    "新增因子相对基础模型有可重复的增量贡献",
                    "影子组合积累足够真实冻结样本"
                ).forEachIndexed { index, text ->
                    Text("${index + 1}. $text", color = V40Ink, fontSize = 10.sp)
                }
            }
        }
    }
}

@Composable
private fun LayerCard40(title: String, subtitle: String, content: @Composable ColumnScope.() -> Unit) {
    Card(colors = CardDefaults.cardColors(containerColor = Color.White), shape = RoundedCornerShape(17.dp)) {
        Column(Modifier.fillMaxWidth().padding(13.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
            Text(title, color = V40Ink, fontWeight = FontWeight.Bold, fontSize = 15.sp)
            Text(subtitle, color = V40Muted, fontSize = 9.sp)
            content()
        }
    }
}

@Composable
private fun ColumnScope.ChainRow40(index: String, title: String, state: String, color: Color) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Surface(color = color, shape = RoundedCornerShape(20.dp)) {
            Text(index, color = Color.White, fontWeight = FontWeight.Bold, fontSize = 9.sp, modifier = Modifier.padding(horizontal = 7.dp, vertical = 4.dp))
        }
        Spacer(Modifier.width(8.dp))
        Text(title, color = V40Ink, fontSize = 10.sp, modifier = Modifier.weight(1f))
        Text(state, color = color, fontSize = 9.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun ColumnScope.ChainDivider40() {
    Spacer(Modifier.width(10.dp).height(4.dp).background(Color(0xFFDDE2EE), RoundedCornerShape(2.dp)))
}

@Composable
private fun KeyRow40(label: String, value: String) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
        Text(label, color = V40Muted, fontSize = 9.sp, modifier = Modifier.width(118.dp))
        Text(value, color = V40Ink, fontSize = 9.sp, fontWeight = FontWeight.Medium, modifier = Modifier.weight(1f))
    }
}

@Composable
private fun EvidenceStatus40(label: String, note: String, state: String) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(label, color = V40Ink, fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
            Text(note, color = V40Muted, fontSize = 8.sp)
        }
        StatusPill40(state, if (state == "不生产") V40Muted else V40Amber)
    }
}

@Composable
private fun GateRow40(label: String, ok: Boolean, detail: String) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(if (ok) "✓" else "○", color = if (ok) V40Green else V40Amber, fontWeight = FontWeight.Bold, modifier = Modifier.width(20.dp))
        Column(Modifier.weight(1f)) {
            Text(label, color = V40Ink, fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
            Text(detail, color = V40Muted, fontSize = 8.sp)
        }
    }
}

@Composable
private fun EvidenceChip40(label: String, available: Boolean) {
    Surface(color = if (available) V40SoftGreen else V40SoftGray, shape = RoundedCornerShape(8.dp)) {
        Text(
            if (available) "$label ✓" else "$label —",
            color = if (available) V40Green else V40Muted,
            fontSize = 8.sp,
            modifier = Modifier.padding(horizontal = 6.dp, vertical = 3.dp)
        )
    }
}

@Composable
private fun StatusPill40(text: String, color: Color) {
    Surface(color = color.copy(alpha = 0.11f), shape = RoundedCornerShape(18.dp)) {
        Text(text, color = color, fontSize = 8.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(horizontal = 7.dp, vertical = 4.dp))
    }
}

@Composable
private fun Notice40(text: String) {
    Surface(color = V40SoftBlue, shape = RoundedCornerShape(10.dp)) {
        Text(text, color = V40Blue, fontSize = 8.sp, modifier = Modifier.fillMaxWidth().padding(8.dp))
    }
}

internal suspend fun fetchLayerRadar40(): LayerRadar40 = withContext(Dispatchers.IO) {
    val root = JSONObject(BackendClient.fetchText(RADAR40_PATH))
    val availability = mutableMapOf<String, String>()
    root.optJSONObject("factorAvailability")?.let { o ->
        val keys = o.keys()
        while (keys.hasNext()) {
            val key = keys.next()
            availability[key] = o.optString(key)
        }
    }

    val sectorArray = root.optJSONArray("mainlines") ?: JSONArray()
    val sectors = (0 until sectorArray.length()).mapNotNull { index ->
        val x = sectorArray.optJSONObject(index) ?: return@mapNotNull null
        LayerSector40(
            code = x.optString("boardCode"),
            name = x.optString("name", "未命名板块"),
            type = x.optString("type", "板块"),
            stage = x.optString("stage", "RADAR"),
            formation = num40(x, "formationScore"),
            accumulation = num40(x, "accumulationScore"),
            extensionPenalty = num40(x, "priceExtensionPenalty"),
            chaseRisk = x.optString("chaseRisk", "MEDIUM"),
            changePct = num40(x, "changePct"),
            flowPct = num40(x, "mainFlowPct"),
            breadthPct = num40(x, "breadthPct"),
            rs20 = num40(x, "RS20"),
            rs60 = num40(x, "RS60"),
            mta = x.optString("MTA", "—"),
            reason = x.optString("reasonZh", "—")
        )
    }

    val stocks = mutableListOf<LayerStock40>()
    root.optJSONObject("stocks")?.let { o ->
        val keys = o.keys()
        while (keys.hasNext()) {
            val code = keys.next()
            val x = o.optJSONObject(code) ?: continue
            stocks += LayerStock40(
                code = code,
                name = x.optString("name", code),
                sector = x.optString("sector", "未分类"),
                stage = x.optString("mainlineStage", "RADAR"),
                action = x.optString("actionZh", "观察"),
                changePct = num40(x, "changePct"),
                amount = num40(x, "amount"),
                turnover = num40(x, "turnover"),
                volumeRatio = numAny40(x, "volumeRatio", "volumeRatio5d", "amountRatio5d"),
                baseEvidence = num40(x, "baseScore"),
                marginEvidence = numAny40(x, "marginFactorScore", "marginScore"),
                etfEvidence = numAny40(x, "etfFactorScore", "etfScore"),
                flowEvidence = num40(x, "flowScore"),
                mainFlowPct = num40(x, "mainFlowPct"),
                chaseRisk = x.optString("chaseRisk", "MEDIUM"),
                reason = x.optString("reasonZh", "—")
            )
        }
    }
    val slow = root.optJSONObject("slowMoneyFactor") ?: JSONObject()
    LayerRadar40(
        date = root.optString("date", "—"),
        capturedAt = root.optString("capturedAt", "—"),
        status = root.optString("status", "Unknown"),
        strategyVersion = root.optString("strategyVersion", "—"),
        dataSource = root.optString("dataSource", "—"),
        factorAvailability = availability,
        slowDataDate = slow.optString("dataDate", ""),
        slowState = slow.optString("state", "unavailable"),
        sectors = sectors,
        stocks = stocks
    )
}

private fun num40(o: JSONObject, key: String): Double? {
    if (!o.has(key) || o.isNull(key)) return null
    return when (val value = o.opt(key)) {
        is Number -> value.toDouble()
        else -> value?.toString()?.toDoubleOrNull()
    }
}

private fun numAny40(o: JSONObject, vararg keys: String): Double? =
    keys.firstNotNullOfOrNull { num40(o, it) }

private fun stageOrder40(stage: String): Int = when (stage.uppercase()) {
    "RADAR" -> 0
    "EMERGING" -> 1
    "CONFIRMING" -> 2
    "ESTABLISHED" -> 3
    "OVERHEATED" -> 4
    "FADING" -> 5
    else -> 6
}

private fun chaseOrder40(risk: String): Int = when (risk.uppercase()) {
    "LOW" -> 0
    "MEDIUM" -> 1
    "HIGH" -> 2
    else -> 3
}

private fun stageZh40(stage: String): String = when (stage.uppercase()) {
    "RADAR" -> "潜在雷达"
    "EMERGING" -> "潜在主线"
    "CONFIRMING" -> "主线确认"
    "ESTABLISHED" -> "已成主线"
    "OVERHEATED" -> "过热"
    "FADING" -> "衰退"
    else -> "观察"
}

private fun stageStatusZh40(status: String): String = when (status.uppercase()) {
    "RADARLIVE" -> "盘中滚动"
    "OFFICIAL" -> "正式冻结"
    else -> status.ifBlank { "未知状态" }
}

private fun stageColor40(stage: String): Color = when (stage.uppercase()) {
    "RADAR", "EMERGING" -> V40Blue
    "CONFIRMING", "ESTABLISHED" -> V40Green
    "OVERHEATED" -> V40Red
    "FADING" -> V40Muted
    else -> V40Amber
}

private fun chaseZh40(risk: String): String = when (risk.uppercase()) {
    "LOW" -> "追高低"
    "MEDIUM" -> "追高中"
    "HIGH" -> "追高高"
    else -> "待核验"
}

private fun pct40(v: Double?): String = v?.let { String.format("%+.2f%%", it) } ?: "—"
private fun plainPct40(v: Double?): String = v?.let { String.format("%.2f%%", it) } ?: "—"
private fun number40(v: Double?): String = v?.let { String.format("%.2f", it) } ?: "—"
private fun amount40(v: Double?): String = when {
    v == null -> "—"
    v >= 100_000_000 -> String.format("%.2f亿", v / 100_000_000.0)
    v >= 10_000 -> String.format("%.0f万", v / 10_000.0)
    else -> String.format("%.0f", v)
}

private fun shortTime40(value: String): String = value.substringAfter('T', value).take(8)
