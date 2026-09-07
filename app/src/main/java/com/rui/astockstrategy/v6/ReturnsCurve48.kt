package com.rui.astockstrategy.v6
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.json.JSONObject

@Composable
fun ReturnsCurve48(report: JSONObject?, error: String?) {
    var cumulative by remember { mutableStateOf(false) }
    val a=report?.optJSONArray("rows")
    val rows=(0 until (a?.length()?:0)).mapNotNull { a?.optJSONObject(it) }
    val key=if(cumulative) "cumulativeReturnPct" else "dailyReturnPct"
    val points=rows.map { it.optDouble(key,Double.NaN).takeIf { x -> x.isFinite() } }
    val valid=points.filterNotNull(); val blue=Color(0xFF3557D4)
    Card(colors=CardDefaults.cardColors(containerColor=Color.White)) {
        Column(Modifier.fillMaxWidth().padding(12.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
            Text("2000万阶段收益",fontWeight=FontWeight.Bold,fontSize=16.sp)
            Row { FilterChip(selected=!cumulative,onClick={cumulative=false},label={Text("每日收益率")}); Spacer(Modifier.width(8.dp)); FilterChip(selected=cumulative,onClick={cumulative=true},label={Text("累计收益率")}) }
            if(valid.isEmpty()) Text(error?:"收盘数据不足，等待核算",fontSize=12.sp)
            else {
                val low=minOf(valid.minOrNull()?:0.0,0.0); val high=maxOf(valid.maxOrNull()?:0.0,0.0); val span=(high-low).coerceAtLeast(.1)
                Text("${String.format("%.2f",high)}%",fontSize=10.sp)
                Canvas(Modifier.fillMaxWidth().height(130.dp)) {
                    val margin=8.dp.toPx(); val h=size.height-margin*2; val w=size.width-margin*2
                    val zero=margin+(high/span).toFloat()*h
                    drawLine(Color.LightGray,Offset(margin,zero),Offset(size.width-margin,zero))
                    var previous:Offset?=null
                    points.forEachIndexed { i,v ->
                        if(v==null) previous=null else {
                            val p=Offset(margin+if(points.size>1) w*i/(points.size-1) else w/2,margin+((high-v)/span).toFloat()*h)
                            previous?.let { drawLine(blue,it,p,strokeWidth=2.dp.toPx()) }; drawCircle(blue,3.dp.toPx(),p); previous=p
                        }
                    }
                }
                Text("${String.format("%.2f",low)}% · ${rows.firstOrNull()?.optString("date")} — ${rows.lastOrNull()?.optString("date")}",fontSize=10.sp)
            }
            Text("日期       本日收益       日收益率",fontSize=11.sp,fontWeight=FontWeight.Bold)
            rows.asReversed().take(30).forEach { r ->
                val pnl=r.optDouble("dailyPnl",Double.NaN); val pct=r.optDouble("dailyReturnPct",Double.NaN)
                Row(Modifier.fillMaxWidth()) {
                    Text(r.optString("date"),Modifier.weight(1f),fontSize=11.sp)
                    Text(if(pnl.isFinite()) String.format("%+.2f",pnl) else "基准/缺口",Modifier.weight(1f),fontSize=11.sp)
                    Text(if(pct.isFinite()) String.format("%+.3f%%",pct) else "—",Modifier.weight(1f),fontSize=11.sp)
                }
            }
            Text(report?.optString("formulaZh")?:"本日收益÷前一日收盘总资产；净入金不计盈利。",fontSize=10.sp)
            Text(report?.optString("baselineNoteZh").orEmpty(),fontSize=10.sp)
            Text(report?.optString("sourceZh").orEmpty(),fontSize=10.sp,color=Color.Gray)
        }
    }
}
