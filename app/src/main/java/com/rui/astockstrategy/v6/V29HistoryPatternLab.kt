package com.rui.astockstrategy.v6

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.max
import kotlin.math.min

private const val HISTORY_PATH_29 = "astock_history/latest.json"
private val HBg29 = Color(0xFFF5F7FB)
private val HBlue29 = Color(0xFF3557D4)
private val HRed29 = Color(0xFFD84343)
private val HGreen29 = Color(0xFF15966A)
private val HAmber29 = Color(0xFFAE6A00)
private val HMuted29 = Color(0xFF747B8D)
private val HGrid29 = Color(0xFFE6EAF2)

private fun d29(o: JSONObject?, key: String): Double? {
    if (o == null || !o.has(key) || o.isNull(key)) return null
    return when (val v = o.opt(key)) {
        is Number -> v.toDouble()
        else -> v?.toString()?.toDoubleOrNull()
    }
}
private fun p29(v: Double?): String = v?.let { String.format("%+.2f%%", it * 100.0) } ?: "—"
private fun n29(v: Double?): String = v?.let { String.format("%.2f", it) } ?: "—"
private fun c29(v: Double?): Color = if ((v ?: 0.0) >= 0) HRed29 else HGreen29

private suspend fun fetchHistory29(): JSONObject = withContext(Dispatchers.IO) {
    JSONObject(BackendClient.fetchText(HISTORY_PATH_29))
}

private data class Horizon29(val label: String, val days: Int, val members: Int, val mean: Double?, val median: Double?, val hit: Double?, val alpha: Double?, val p25: Double?, val p75: Double?)
private data class PathPoint29(val day: Int, val mean: Double?, val median: Double?, val alpha: Double?)
private data class Scatter29(val name: String, val code: String, val mfe: Double, val mae: Double, val ret5: Double?)
private data class Cond29(val name: String, val count: Int, val ret5: Double?, val alpha5: Double?, val hit5: Double?)

private fun horizons29(root: JSONObject?): List<Horizon29> {
    val h = root?.optJSONObject("overall")?.optJSONObject("horizons") ?: return emptyList()
    return listOf("1D" to 1, "2D" to 2, "3D" to 3, "5D" to 5, "10D" to 10, "20D" to 20, "40D" to 40, "60D" to 60, "120D" to 120, "250D" to 250).map { (label, days) ->
        val x = h.optJSONObject(label)
        Horizon29(label, days, x?.optInt("members") ?: 0, d29(x,"meanReturn"), d29(x,"medianReturn"), d29(x,"hitRate"), d29(x,"medianAlpha"), d29(x,"p25"), d29(x,"p75"))
    }
}
private fun path29(a: JSONArray?): List<PathPoint29> {
    if (a == null) return emptyList()
    return (0 until a.length()).mapNotNull { i -> a.optJSONObject(i)?.let { PathPoint29(it.optInt("day"), d29(it,"meanReturn"), d29(it,"medianReturn"), d29(it,"meanAlpha")) } }
}
private fun scatter29(a: JSONArray?): List<Scatter29> {
    if (a == null) return emptyList()
    return (0 until a.length()).mapNotNull { i ->
        val x = a.optJSONObject(i) ?: return@mapNotNull null
        val mfe = d29(x,"mfe") ?: return@mapNotNull null
        val mae = d29(x,"mae") ?: return@mapNotNull null
        Scatter29(x.optString("name"), x.optString("code"), mfe, mae, d29(x,"fiveDayReturn"))
    }
}
private fun cond29(a: JSONArray?): List<Cond29> {
    if (a == null) return emptyList()
    return (0 until a.length()).mapNotNull { i -> a.optJSONObject(i)?.let { Cond29(it.optString("name"), it.optInt("sampleCount"), d29(it,"fiveDayMedianReturn"), d29(it,"fiveDayMedianAlpha"), d29(it,"fiveDayHitRate")) } }
}

@Composable
fun HistoryPatternLabScreen29() {
    var data by remember { mutableStateOf<JSONObject?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var tab by remember { mutableStateOf("总览") }
    var horizonMode by remember { mutableStateOf("中短线") }
    var sampleSourceMode by remember { mutableStateOf("真实样本") }
    LaunchedEffect(Unit) {
        while (true) {
            runCatching { fetchHistory29() }.onSuccess { data = it; error = null }.onFailure { error = "动态历史研究数据暂未同步" }
            delay(60000)
        }
    }
    val rawHistory = data
    val reconstructionReady = rawHistory?.optJSONObject("reconstruction") != null
    val sourceChoices = if (reconstructionReady) listOf("真实样本", "历史重建") else listOf("真实样本")
    if (!reconstructionReady && sampleSourceMode == "历史重建") sampleSourceMode = "真实样本"
    val d = if (sampleSourceMode == "历史重建") rawHistory?.optJSONObject("reconstruction") else rawHistory
    val overall = d?.optJSONObject("overall")
    val vitals = d?.optJSONObject("vitals")
    val best = if (horizonMode == "中短线") d?.optJSONObject("bestHoldingShort") ?: d?.optJSONObject("bestHolding") else d?.optJSONObject("bestHoldingLong")
    val trend = d?.optJSONObject("edgeTrend")
    val judge = trend?.optJSONObject("judgement")
    val allHs = horizons29(d)
    val shortLabels = setOf("1D","2D","3D","5D","10D","20D")
    val longLabels = setOf("20D","40D","60D","120D","250D")
    val hs = allHs.filter { if (horizonMode == "中短线") it.label in shortLabels else it.label in longLabels }
    val path = path29(d?.optJSONArray("eventPath")).filter { it.day == 0 || if (horizonMode == "中短线") it.day <= 20 else it.day >= 20 }
    val scatter = scatter29(d?.optJSONArray("riskScatter"))
    val conditions = d?.optJSONObject("conditions")
    val bestText = if (horizonMode == "中短线") vitals?.optString("bestShortHoldingZh") ?: vitals?.optString("bestHoldingZh") else vitals?.optString("bestLongHoldingZh")

    LazyColumn(
        modifier = Modifier.fillMaxSize().background(HBg29),
        contentPadding = PaddingValues(14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item {
            Card(shape = RoundedCornerShape(18.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
                Column(Modifier.fillMaxWidth().padding(15.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("动态历史形态实验室", fontWeight = FontWeight.Bold, fontSize = 18.sp)
                            Text(
                                if (sampleSourceMode == "历史重建") "行业板块周频历史重建 · 研究用 · 不计入样本外战绩"
                                else "真实冻结样本持续累积 · 每日重算 · 不删除失败案例",
                                color = HMuted29, fontSize = 10.sp
                            )
                        }
                        Text(d?.optString("updatedAt")?.replace("T"," ")?.take(16) ?: "—", color = HBlue29, fontSize = 9.sp)
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        HMetric29("样本数", overall?.optInt("sampleCount")?.toString() ?: "—", HBlue29, Modifier.weight(1f))
                        HMetric29("可信度", overall?.optString("confidenceZh") ?: "—", HAmber29, Modifier.weight(1f))
                        HMetric29("近期趋势", judge?.optString("stateZh") ?: "—", when(judge?.optInt("score")){1->HRed29;-1->HGreen29;else->HMuted29}, Modifier.weight(1f))
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        HMetric29("最佳持有", bestText ?: "待样本", HBlue29, Modifier.weight(1f))
                        HMetric29("长期有效性", vitals?.optString("longTermValidityZh") ?: "待样本", HMuted29, Modifier.weight(1f))
                        HMetric29("近期判断", vitals?.optString("recentTrendZh") ?: "待样本", HMuted29, Modifier.weight(1f))
                    }
                    Text(vitals?.optString("currentAdviceZh") ?: "继续积累真实样本。", color = HMuted29, fontSize = 10.sp)
                }
            }
        }
        if (error != null) item { HNotice29(error!!, HAmber29) }
        item { HSection29("样本来源") }
        item { HChoice29(sourceChoices, sampleSourceMode) { sampleSourceMode = it } }
        if (sampleSourceMode == "历史重建") item { ReconstructionNotice30(d) }
        else item { HNotice29("真实样本：只统计当时真实冻结并持续跟踪的正式样本，用于样本外验证。", HBlue29) }
        item { HChoice29(listOf("中短线","中长线"), horizonMode) { horizonMode = it } }
        item { HChoice29(listOf("总览","路径","风险","条件"), tab) { tab = it } }

        when (tab) {
            "总览" -> {
                item { HSection29("多周期历史表现") }
                item { HorizonBars29(hs) }
                item { HorizonTable29(hs) }
                item { HSection29("形态生命体征") }
                item {
                    HCard29 {
                        HKey29("长期有效性", vitals?.optString("longTermValidityZh") ?: "待样本")
                        HKey29("近期有效性", vitals?.optString("recentTrendZh") ?: "待样本")
                        HKey29("样本可信度", vitals?.optString("sampleConfidenceZh") ?: "待样本")
                        HKey29("当前最佳周期", bestText ?: "待样本")
                        HKey29("判断依据", best?.optString("reasonZh") ?: "成熟样本不足")
                    }
                }
                item { HSection29("历史优势变化") }
                item { EdgeTrend29(trend) }
                item { HSection29("样本累计增长") }
                item { SampleGrowthChart29(d?.optJSONArray("sampleGrowth")) }
            }
            "路径" -> {
                item { HSection29("事件研究累计收益路径") }
                item { HNotice29("横轴为信号后交易日。均值、中位数和超额收益会随每天新增成熟样本自动变化。", HBlue29) }
                item { EventPathChart29(path) }
                item { HSection29("路径区间") }
                item { PathRangeTable29(hs) }
                item { HSection29("历史路径分型") }
                item { PathClustersCard29(d?.optJSONObject("pathClusters")) }
            }
            "风险" -> {
                item { HSection29("最大有利 / 最大不利波动") }
                item { HNotice29("每个点代表一个真实冻结样本。右上更有吸引力；左下代表回撤较大且上行空间不足。", HBlue29) }
                item { RiskScatterChart29(scatter) }
                item {
                    HCard29 {
                        HKey29("历史中位最大有利涨幅", p29(d29(overall,"medianMFE")))
                        HKey29("历史中位最大不利跌幅", p29(d29(overall,"medianMAE")))
                        HKey29("历史中位最大回撤", p29(d29(overall,"medianMaxDrawdown")))
                    }
                }
                item { HSection29("未来收益分布") }
                item {
                    val target = if (horizonMode == "中短线") "5D" else "60D"
                    ReturnDistribution29(d?.optJSONObject("returnDistributions")?.optJSONObject(target), target)
                }
                item { HSection29("成功 / 失败样本对比") }
                item { SuccessFailureCard29(d?.optJSONObject("successFailure")) }
                item { HSection29("典型历史案例") }
                item { HistoryExamplesCard29(d?.optJSONObject("successFailure")) }
            }
            else -> {
                item { HSection29("市场状态适配") }
                val regimes = cond29(conditions?.optJSONArray("byRegime"))
                if (regimes.isEmpty()) item { HNotice29("不同市场状态的成熟样本仍不足，继续积累。", HMuted29) }
                else items(regimes) { ConditionRow29(it) }
                item { HSection29("股票池条件表现") }
                val pools = cond29(conditions?.optJSONArray("byPool"))
                if (pools.isEmpty()) item { HNotice29("股票池条件样本仍不足。", HMuted29) }
                else items(pools.take(12)) { ConditionRow29(it) }
                item { HSection29("主线阶段 × 追高风险") }
                val stages = cond29(conditions?.optJSONArray("byMainlineState"))
                val chase = cond29(conditions?.optJSONArray("byChaseRisk"))
                if (stages.isEmpty() && chase.isEmpty()) item {
                    HNotice29(
                        if (sampleSourceMode == "历史重建") "重建阶段 / 追高风险条件样本不足；重建标签由固定v3.0规则生成，不回写为当时真实标签。"
                        else "只有原始冻结快照真实记录主线阶段 / 追高风险后才参与统计；当前不会做代理补造。",
                        HAmber29
                    )
                }
                else {
                    items(stages) { ConditionRow29(it) }
                    items(chase) { ConditionRow29(it) }
                }
                item { StageChaseHeat29(conditions?.optJSONArray("stageByChase")) }
            }
        }

        item { HSection29("数据口径") }
        item { HNotice29(d?.optString("sourcePolicyZh") ?: "当前只统计真实冻结样本。", HMuted29) }
    }
}

@Composable private fun HMetric29(label:String,value:String,color:Color,modifier:Modifier=Modifier){ Column(modifier){ Text(label,color=HMuted29,fontSize=9.sp); Text(value,color=color,fontWeight=FontWeight.Bold,fontSize=12.sp) } }
@Composable private fun HSection29(s:String){ Text(s,fontWeight=FontWeight.Bold,fontSize=14.sp) }
@Composable private fun HCard29(content:@Composable ColumnScope.()->Unit){ Card(shape=RoundedCornerShape(16.dp),colors=CardDefaults.cardColors(containerColor=Color.White)){ Column(Modifier.fillMaxWidth().padding(13.dp),verticalArrangement=Arrangement.spacedBy(6.dp),content=content) } }
@Composable private fun HKey29(k:String,v:String){ Row(Modifier.fillMaxWidth()){ Text(k,Modifier.weight(1f),color=HMuted29,fontSize=10.sp); Text(v,fontWeight=FontWeight.SemiBold,fontSize=10.sp) } }
@Composable private fun HNotice29(s:String,color:Color){ Surface(color=Color.White,shape=RoundedCornerShape(14.dp)){ Text(s,Modifier.fillMaxWidth().padding(12.dp),color=color,fontSize=10.sp) } }
@Composable private fun HChoice29(items:List<String>,value:String,onChange:(String)->Unit){ SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()){ items.forEachIndexed{ i,x -> SegmentedButton(selected=x==value,onClick={onChange(x)},shape=SegmentedButtonDefaults.itemShape(i,items.size),label={Text(x,fontSize=10.sp)}) } } }

@Composable
private fun HorizonBars29(hs:List<Horizon29>){
    HCard29 {
        if(hs.none{it.median!=null}) Text("成熟样本不足",color=HMuted29,fontSize=10.sp)
        else {
            val values=hs.flatMap{listOfNotNull(it.mean,it.median)}
            val scale=max(0.01, values.maxOfOrNull{kotlin.math.abs(it)} ?: 0.01)
            Canvas(Modifier.fillMaxWidth().height(160.dp)){
                val base=size.height/2f
                drawLine(HGrid29,Offset(0f,base),Offset(size.width,base),1f)
                val group=size.width/hs.size
                hs.forEachIndexed{i,h->
                    listOf(h.mean to HBlue29,h.median to HAmber29).forEachIndexed{j,pair->
                        val v=pair.first ?: return@forEachIndexed
                        val bh=(kotlin.math.abs(v)/scale*size.height*0.38).toFloat()
                        val x=group*i+group*(0.24f+j*0.24f)
                        val top=if(v>=0) base-bh else base
                        drawRect(pair.second,Offset(x,top),androidx.compose.ui.geometry.Size(group*0.18f,bh))
                    }
                }
            }
            Row(horizontalArrangement=Arrangement.spacedBy(14.dp)){ Text("■ 平均收益",color=HBlue29,fontSize=9.sp); Text("■ 中位收益",color=HAmber29,fontSize=9.sp) }
            Row(Modifier.fillMaxWidth()){ hs.forEach{ Text(it.label,Modifier.weight(1f),fontSize=9.sp,color=HMuted29) } }
        }
    }
}

@Composable
private fun HorizonTable29(hs:List<Horizon29>){
    HCard29 {
        Row{ listOf("周期","样本","中位","胜率","超额").forEachIndexed{i,x-> Text(x,Modifier.weight(if(i==0)0.75f else 1f),color=HMuted29,fontSize=9.sp) } }
        hs.forEach{ h->
            Row{ Text(h.label,Modifier.weight(.75f),fontWeight=FontWeight.Bold,fontSize=10.sp); Text(h.members.toString(),Modifier.weight(1f),fontSize=10.sp); Text(p29(h.median),Modifier.weight(1f),color=c29(h.median),fontSize=10.sp); Text(p29(h.hit),Modifier.weight(1f),fontSize=10.sp); Text(p29(h.alpha),Modifier.weight(1f),color=c29(h.alpha),fontSize=10.sp) }
        }
    }
}

@Composable
private fun EdgeTrend29(t:JSONObject?){
    HCard29 {
        val full=t?.optJSONObject("full")
        val r60=t?.optJSONObject("recent60")
        val r20=t?.optJSONObject("recent20")
        val j=t?.optJSONObject("judgement")
        listOf("全历史" to full,"最近60样本" to r60,"最近20样本" to r20).forEach{(name,x)->
            Row{ Text(name,Modifier.weight(1f),fontSize=10.sp); Text("5日超额 ${p29(d29(x,"fiveDayMedianAlpha"))}",Modifier.width(120.dp),color=c29(d29(x,"fiveDayMedianAlpha")),fontSize=10.sp); Text("胜率 ${p29(d29(x,"fiveDayHitRate"))}",fontSize=10.sp) }
        }
        HorizontalDivider()
        Text("动态判断：${j?.optString("stateZh") ?: "样本不足"}",fontWeight=FontWeight.Bold,fontSize=11.sp)
        Text(j?.optString("reasonZh") ?: "继续积累成熟样本",color=HMuted29,fontSize=9.sp)
    }
}

@Composable
private fun EventPathChart29(points:List<PathPoint29>){
    HCard29 {
        if(points.size<2){ Text("成熟路径样本不足",color=HMuted29,fontSize=10.sp); return@HCard29 }
        val vals=points.flatMap{listOfNotNull(it.mean,it.median,it.alpha)}
        val lo=min(-0.01, vals.minOrNull() ?: -0.01)
        val hi=max(0.01, vals.maxOrNull() ?: 0.01)
        val range=hi-lo
        Canvas(Modifier.fillMaxWidth().height(190.dp)){
            fun y(v:Double)=((hi-v)/range*size.height*0.82+size.height*0.08).toFloat()
            val maxDay=max(1,points.maxOf{it.day})
            fun x(day:Int)=(day.toFloat()/maxDay*size.width).coerceIn(0f,size.width)
            drawLine(HGrid29,Offset(0f,y(0.0)),Offset(size.width,y(0.0)),1f)
            fun line(selector:(PathPoint29)->Double?,color:Color){
                val p=Path()
                var first=true
                points.forEach{pt-> selector(pt)?.let{v-> if(first){p.moveTo(x(pt.day),y(v));first=false}else p.lineTo(x(pt.day),y(v))} }
                drawPath(p,color,style=androidx.compose.ui.graphics.drawscope.Stroke(width=3f))
            }
            line({it.mean},HBlue29); line({it.median},HAmber29); line({it.alpha},HRed29)
        }
        Row(horizontalArrangement=Arrangement.spacedBy(10.dp)){ Text("— 平均",color=HBlue29,fontSize=9.sp);Text("— 中位",color=HAmber29,fontSize=9.sp);Text("— 超额",color=HRed29,fontSize=9.sp) }
        Row(Modifier.fillMaxWidth()){ points.forEach{ Text("D+${it.day}",Modifier.weight(1f),fontSize=8.sp,color=HMuted29) } }
    }
}

@Composable
private fun PathRangeTable29(hs:List<Horizon29>){ HCard29 { hs.filter{it.members>0}.forEach{h-> Row{ Text(h.label,Modifier.width(42.dp),fontWeight=FontWeight.Bold,fontSize=10.sp);Text("25% ${p29(h.p25)}",Modifier.weight(1f),fontSize=10.sp);Text("中位 ${p29(h.median)}",Modifier.weight(1f),fontSize=10.sp);Text("75% ${p29(h.p75)}",Modifier.weight(1f),fontSize=10.sp) } } } }

@Composable
private fun RiskScatterChart29(points:List<Scatter29>){
    HCard29 {
        if(points.isEmpty()){ Text("MFE / MAE 样本尚未成熟",color=HMuted29,fontSize=10.sp); return@HCard29 }
        val xmin=min(-0.01,points.minOf{it.mae})
        val xmax=max(0.01,points.maxOf{it.mae})
        val ymin=min(-0.01,points.minOf{it.mfe})
        val ymax=max(0.01,points.maxOf{it.mfe})
        Canvas(Modifier.fillMaxWidth().height(220.dp)){
            fun x(v:Double)=((v-xmin)/(xmax-xmin)*size.width).toFloat()
            fun y(v:Double)=((ymax-v)/(ymax-ymin)*size.height).toFloat()
            drawLine(HGrid29,Offset(x(0.0),0f),Offset(x(0.0),size.height),1f); drawLine(HGrid29,Offset(0f,y(0.0)),Offset(size.width,y(0.0)),1f)
            points.forEach{p-> drawCircle(if((p.ret5?:0.0)>=0) HRed29 else HGreen29,5f,Offset(x(p.mae),y(p.mfe)),alpha=.65f) }
        }
        Text("横轴：MAE（越左回撤越大）　纵轴：MFE（越高上行空间越大）",color=HMuted29,fontSize=8.sp)
    }
}

@Composable
private fun ConditionRow29(x:Cond29){
    HCard29 {
        Row(verticalAlignment=Alignment.CenterVertically){ Column(Modifier.weight(1f)){ Text(x.name,fontWeight=FontWeight.Bold,fontSize=11.sp);Text("样本 ${x.count}",color=HMuted29,fontSize=8.sp) }; Column(horizontalAlignment=Alignment.End){ Text("5日中位 ${p29(x.ret5)}",color=c29(x.ret5),fontWeight=FontWeight.Bold,fontSize=10.sp);Text("超额 ${p29(x.alpha5)} · 胜率 ${p29(x.hit5)}",color=HMuted29,fontSize=9.sp) } }
    }
}


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
        Text(o?.optString("definitionZh") ?: "", color = HMuted29, fontSize = 8.sp)
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
