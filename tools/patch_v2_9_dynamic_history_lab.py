from pathlib import Path

root = Path('app/src/main/java/com/rui/astockstrategy/v6')
root.mkdir(parents=True, exist_ok=True)
ui = root / 'V29HistoryPatternLab.kt'
ui.write_text(r'''package com.rui.astockstrategy.v6

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
import java.net.HttpURLConnection
import java.net.URL
import kotlin.math.max
import kotlin.math.min

private const val HISTORY_URL_29 = "https://raw.githubusercontent.com/cskjin940509-ops/cskjin/main/astock_history/latest.json"
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
    val c = URL(HISTORY_URL_29).openConnection() as HttpURLConnection
    c.connectTimeout = 8000
    c.readTimeout = 8000
    c.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android 16)")
    c.setRequestProperty("Cache-Control", "no-cache")
    try {
        if (c.responseCode !in 200..299) error("HTTP ${c.responseCode}")
        JSONObject(c.inputStream.bufferedReader().use { it.readText() })
    } finally { c.disconnect() }
}

private data class Horizon29(val label: String, val days: Int, val members: Int, val mean: Double?, val median: Double?, val hit: Double?, val alpha: Double?, val p25: Double?, val p75: Double?)
private data class PathPoint29(val day: Int, val mean: Double?, val median: Double?, val alpha: Double?)
private data class Scatter29(val name: String, val code: String, val mfe: Double, val mae: Double, val ret5: Double?)
private data class Cond29(val name: String, val count: Int, val ret5: Double?, val alpha5: Double?, val hit5: Double?)

private fun horizons29(root: JSONObject?): List<Horizon29> {
    val h = root?.optJSONObject("overall")?.optJSONObject("horizons") ?: return emptyList()
    return listOf("1D" to 1, "5D" to 5, "10D" to 10, "20D" to 20, "60D" to 60).map { (label, days) ->
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
    LaunchedEffect(Unit) {
        while (true) {
            runCatching { fetchHistory29() }.onSuccess { data = it; error = null }.onFailure { error = "动态历史研究数据暂未同步" }
            delay(60000)
        }
    }
    val d = data
    val overall = d?.optJSONObject("overall")
    val vitals = d?.optJSONObject("vitals")
    val best = d?.optJSONObject("bestHolding")
    val trend = d?.optJSONObject("edgeTrend")
    val judge = trend?.optJSONObject("judgement")
    val hs = horizons29(d)
    val path = path29(d?.optJSONArray("eventPath"))
    val scatter = scatter29(d?.optJSONArray("riskScatter"))
    val conditions = d?.optJSONObject("conditions")

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
                            Text("真实冻结样本持续累积 · 每日重算 · 不删除失败案例", color = HMuted29, fontSize = 10.sp)
                        }
                        Text(d?.optString("updatedAt")?.replace("T"," ")?.take(16) ?: "—", color = HBlue29, fontSize = 9.sp)
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        HMetric29("样本数", overall?.optInt("sampleCount")?.toString() ?: "—", HBlue29, Modifier.weight(1f))
                        HMetric29("可信度", overall?.optString("confidenceZh") ?: "—", HAmber29, Modifier.weight(1f))
                        HMetric29("近期趋势", judge?.optString("stateZh") ?: "—", when(judge?.optInt("score")){1->HRed29;-1->HGreen29;else->HMuted29}, Modifier.weight(1f))
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        HMetric29("最佳持有", vitals?.optString("bestHoldingZh") ?: "待样本", HBlue29, Modifier.weight(1f))
                        HMetric29("长期有效性", vitals?.optString("longTermValidityZh") ?: "待样本", HMuted29, Modifier.weight(1f))
                        HMetric29("近期判断", vitals?.optString("recentTrendZh") ?: "待样本", HMuted29, Modifier.weight(1f))
                    }
                    Text(vitals?.optString("currentAdviceZh") ?: "继续积累真实样本。", color = HMuted29, fontSize = 10.sp)
                }
            }
        }
        if (error != null) item { HNotice29(error!!, HAmber29) }
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
                        HKey29("当前最佳周期", vitals?.optString("bestHoldingZh") ?: "待样本")
                        HKey29("判断依据", best?.optString("reasonZh") ?: "成熟样本不足")
                    }
                }
                item { HSection29("历史优势变化") }
                item { EdgeTrend29(trend) }
            }
            "路径" -> {
                item { HSection29("事件研究累计收益路径") }
                item { HNotice29("横轴为信号后交易日。均值、中位数和超额收益会随每天新增成熟样本自动变化。", HBlue29) }
                item { EventPathChart29(path) }
                item { HSection29("路径区间") }
                item { PathRangeTable29(hs) }
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
                if (stages.isEmpty() && chase.isEmpty()) item { HNotice29("只有原始冻结快照真实记录主线阶段 / 追高风险后才参与统计；当前不会做代理补造。", HAmber29) }
                else {
                    items(stages) { ConditionRow29(it) }
                    items(chase) { ConditionRow29(it) }
                }
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
        val full=t?.optJSONObject("full"); val r60=t?.optJSONObject("recent60"); val r20=t?.optJSONObject("recent20"); val j=t?.optJSONObject("judgement")
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
        val lo=min(-0.01, vals.minOrNull() ?: -0.01); val hi=max(0.01, vals.maxOrNull() ?: 0.01); val range=hi-lo
        Canvas(Modifier.fillMaxWidth().height(190.dp)){
            fun y(v:Double)=((hi-v)/range*size.height*0.82+size.height*0.08).toFloat()
            val maxDay=max(1,points.maxOf{it.day})
            fun x(day:Int)=(day.toFloat()/maxDay*size.width).coerceIn(0f,size.width)
            drawLine(HGrid29,Offset(0f,y(0.0)),Offset(size.width,y(0.0)),1f)
            fun line(selector:(PathPoint29)->Double?,color:Color){
                val p=Path(); var first=true
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
        val xmin=min(-0.01,points.minOf{it.mae}); val xmax=max(0.01,points.maxOf{it.mae}); val ymin=min(-0.01,points.minOf{it.mfe}); val ymax=max(0.01,points.maxOf{it.mfe})
        Canvas(Modifier.fillMaxWidth().height(220.dp)){
            fun x(v:Double)=((v-xmin)/(xmax-xmin)*size.width).toFloat(); fun y(v:Double)=((ymax-v)/(ymax-ymin)*size.height).toFloat()
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
''', encoding='utf-8')

v6 = root / 'V6Activity.kt'
s = v6.read_text(encoding='utf-8')
old = 'Tab.HISTORY -> HistoryScreen(snapshots, active, quotes, selectedDate) { selectedDate = it }'
new = 'Tab.HISTORY -> HistoryPatternLabScreen29()'
if old in s:
    s = s.replace(old, new, 1)
elif new not in s:
    raise SystemExit('history route anchor not found')
v6.write_text(s, encoding='utf-8')

g = Path('app/build.gradle.kts')
gs = g.read_text(encoding='utf-8')
gs = gs.replace('versionCode = 30', 'versionCode = 31')
gs = gs.replace('versionName = "2.8.0"', 'versionName = "2.9.0"')
if 'versionName = "2.9.0"' not in gs:
    raise SystemExit('v2.9 version bump failed')
g.write_text(gs, encoding='utf-8')

assert ui.exists()
assert 'HistoryPatternLabScreen29()' in v6.read_text(encoding='utf-8')
print('v2.9 dynamic history pattern lab integrated')
