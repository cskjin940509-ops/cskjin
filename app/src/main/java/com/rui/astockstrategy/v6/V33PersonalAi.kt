package com.rui.astockstrategy.v6

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
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
import java.time.ZoneId
import java.time.ZonedDateTime
import kotlin.math.abs

private const val P33_PATH = "astock_ai_portfolio/latest.json"
private const val P33_DEFAULT_CAPITAL = 20000000.0
private const val P33_SCHEMA = 42
private val P33Blue = Color(0xFF3557D4)
private val P33Muted = Color(0xFF747B8D)
private val P33Red = Color(0xFFD84343)
private val P33Green = Color(0xFF15966A)
private val P33Amber = Color(0xFFAE6A00)

private fun d33(o: JSONObject?, k: String): Double? {
    if (o == null || !o.has(k) || o.isNull(k)) return null
    return when (val v = o.opt(k)) { is Number -> v.toDouble(); else -> v?.toString()?.toDoubleOrNull() }
}
private fun money33(v: Double): String = when {
    abs(v) >= 100000000 -> String.format("¥%.2f亿", v / 100000000.0)
    abs(v) >= 10000 -> String.format("¥%.2f万", v / 10000.0)
    else -> String.format("¥%.2f", v)
}
private fun pct33(v: Double): String = String.format("%+.2f%%", v)

private suspend fun fetch33(): JSONObject = withContext(Dispatchers.IO) {
    JSONObject(BackendClient.fetchText(P33_PATH))
}

private object PersonalStore33 {
    private const val PREF = "ai_personal_dynamic_v33"
    private const val KEY = "state"
    fun load(ctx: AppContext): JSONObject {
        val prefs = ctx.getSharedPreferences(PREF, AppContext.MODE_PRIVATE)
        val raw = prefs.getString(KEY, null)
        if (!raw.isNullOrBlank()) {
            val saved = runCatching { JSONObject(raw) }.getOrNull()
            if (saved != null) {
                if (saved.optInt("schemaVersion", 0) < P33_SCHEMA) {
                    val old = d33(saved, "configuredCapital") ?: 1000000.0
                    if (old == 1000000.0) {
                        saved.put("configuredCapital", P33_DEFAULT_CAPITAL)
                        saved.put("cash", (d33(saved, "cash") ?: old) + (P33_DEFAULT_CAPITAL - old))
                        appendDecision33(saved, "资金调整", "本机手动账户", "", 0, null, "模拟容量升级为${money33(P33_DEFAULT_CAPITAL)}；不改写旧持仓和盈亏")
                    }
                    saved.put("schemaVersion", P33_SCHEMA)
                    prefs.edit().putString(KEY, saved.toString()).apply()
                }
                return saved
            }
        }
        return JSONObject().apply {
            put("schemaVersion", P33_SCHEMA); put("configuredCapital", P33_DEFAULT_CAPITAL); put("cash", P33_DEFAULT_CAPITAL); put("realizedPnl", 0.0)
            put("positions", JSONObject()); put("decisions", JSONArray()); put("tradeDate", "")
            put("createdAt", System.currentTimeMillis())
        }
    }
    fun save(ctx: AppContext, s: JSONObject) { ctx.getSharedPreferences(PREF, AppContext.MODE_PRIVATE).edit().putString(KEY, s.toString()).apply() }
}

private fun cnNow33(): ZonedDateTime = ZonedDateTime.now(ZoneId.of("Asia/Shanghai"))

private fun appendDecision33(s: JSONObject, side: String, name: String, code: String, qty: Int, price: Double?, text: String) {
    val a = s.optJSONArray("decisions") ?: JSONArray().also { s.put("decisions", it) }
    a.put(JSONObject().apply {
        put("time", cnNow33().toString()); put("side", side); put("name", name); put("code", code); put("qty", qty)
        if (price != null) put("price", price); put("text", text)
    })
    while (a.length() > 200) a.remove(0)
}

private fun applyCapital33(s0: JSONObject, newCapital: Double): JSONObject {
    val s = JSONObject(s0.toString())
    val old = d33(s, "configuredCapital") ?: P33_DEFAULT_CAPITAL
    val delta = newCapital - old
    s.put("configuredCapital", newCapital)
    s.put("cash", (d33(s, "cash") ?: old) + delta)
    appendDecision33(s, "资金调整", "模拟账户", "", 0, null, "投入本金由${money33(old)}调整为${money33(newCapital)}；差额${money33(delta)}不计入投资收益")
    return s
}

private data class Target33(val code:String,val name:String,val sector:String,val weight:Double,val price:Double,val score:Double)
private fun targets33(data: JSONObject?): List<Target33> {
    val rawTarget = data?.opt("targetPortfolio")
    val a = when (rawTarget) {
        is JSONArray -> rawTarget
        is JSONObject -> rawTarget.optJSONArray("members")
        else -> null
    } ?: return emptyList()
    return (0 until a.length()).mapNotNull { i ->
        val x=a.optJSONObject(i)?:return@mapNotNull null
        val p=d33(x,"referencePrice")?:return@mapNotNull null
        Target33(x.optString("code"),x.optString("name").ifBlank{x.optString("code")},x.optString("sector").ifBlank{"未知"},(d33(x,"targetWeightPct")?:0.0)/100.0,p,d33(x,"score")?:0.0)
    }
}
private fun priceMap33(data: JSONObject?): MutableMap<String,Double> {
    val m=mutableMapOf<String,Double>()
    targets33(data).forEach{m[it.code]=it.price}
    val a=data?.optJSONArray("positions")
    if(a!=null) for(i in 0 until a.length()) { val x=a.optJSONObject(i)?:continue; val p=d33(x,"currentPrice")?:continue; m[x.optString("code")]=p }
    return m
}
private fun nav33(s: JSONObject, prices: Map<String,Double>): Double {
    var n=d33(s,"cash")?:0.0; val ps=s.optJSONObject("positions")?:JSONObject()
    val it=ps.keys(); while(it.hasNext()){ val c=it.next(); val p=ps.optJSONObject(c)?:continue; val px=prices[c]?:d33(p,"avgCost")?:0.0; n += p.optInt("qty")*px }
    return n
}

@Composable
fun PersonalAiPanel33() {
    val ctx=LocalAppContext.current
    var state by remember { mutableStateOf(PersonalStore33.load(ctx)) }
    var data by remember { mutableStateOf<JSONObject?>(null) }
    var capitalText by remember { mutableStateOf(String.format("%.0f",d33(state,"configuredCapital")?:P33_DEFAULT_CAPITAL)) }
    var status by remember { mutableStateOf("等待影子目标组合") }

    LaunchedEffect(Unit){
        while(true){
            runCatching{fetch33()}.onSuccess{ d-> data=d; status="已读取云端影子目标；打开App不会触发策略重算" }.onFailure{status="影子目标组合暂未同步：${it.message ?: it.javaClass.simpleName}"}
            delay(30000)
        }
    }
    val prices=priceMap33(data); val nav=nav33(state,prices); val capital=d33(state,"configuredCapital")?:P33_DEFAULT_CAPITAL; val cash=d33(state,"cash")?:0.0; val pnl=nav-capital
    val pos=state.optJSONObject("positions")?:JSONObject(); val targets=targets33(data); val tmap=targets.associateBy{it.code}; val positionPct=if(nav>0)(nav-cash)/nav*100 else 0.0

    Card(shape=RoundedCornerShape(18.dp),colors=CardDefaults.cardColors(containerColor=Color.White)){
        Column(Modifier.fillMaxWidth().padding(14.dp),verticalArrangement=Arrangement.spacedBy(8.dp)){
            Text("本机手动试算账户",fontWeight=FontWeight.Bold,fontSize=17.sp)
            Text("与上方2000万元后台自动账户分开记账 · 不连接券商",color=P33Muted,fontSize=9.sp)
            Row(horizontalArrangement=Arrangement.spacedBy(8.dp),verticalAlignment=Alignment.CenterVertically){
                OutlinedTextField(value=capitalText,onValueChange={capitalText=it.filter{ch->ch.isDigit()||ch=='.'}},label={Text("投入本金（元）")},singleLine=true,modifier=Modifier.weight(1f))
                Button(onClick={ val v=capitalText.toDoubleOrNull(); if(v!=null&&v>=10000){state=applyCapital33(state,v); PersonalStore33.save(ctx,state); status="模拟本金已调整；策略目标仍以云端预计算结果为准"}else{status="请输入不少于1万元的有效金额"} }){Text("应用")}
            }
            Row(horizontalArrangement=Arrangement.spacedBy(10.dp)){
                PMetric33("总资产",money33(nav),P33Blue,Modifier.weight(1f)); PMetric33("持仓",String.format("%.1f%%",positionPct),P33Blue,Modifier.weight(1f)); PMetric33("现金",money33(cash),P33Muted,Modifier.weight(1f))
            }
            Row(horizontalArrangement=Arrangement.spacedBy(10.dp)){
                PMetric33("累计盈亏",money33(pnl),if(pnl>=0)P33Red else P33Green,Modifier.weight(1f)); PMetric33("目标总仓",String.format("%.1f%%",d33(data,"targetGrossPct") ?: d33(data?.optJSONObject("targetPortfolio"),"grossTargetPct") ?: 0.0),P33Amber,Modifier.weight(1f)); PMetric33("持股数",pos.length().toString(),P33Blue,Modifier.weight(1f))
            }
            Text(status,color=P33Muted,fontSize=8.sp)
            HorizontalDivider()
            Text("我的当前持仓",fontWeight=FontWeight.Bold,fontSize=11.sp)
            if(pos.length()==0) Text("当前模拟账户保持现金，等待影子目标组合出现。",color=P33Muted,fontSize=9.sp)
            else {
                val ks=mutableListOf<String>(); val it=pos.keys(); while(it.hasNext())ks+=it.next()
                ks.sortedByDescending{c->(pos.optJSONObject(c)?.optInt("qty")?:0)*(prices[c]?:0.0)}.forEach{c->
                    val p=pos.optJSONObject(c)?:return@forEach; val px=prices[c]?:d33(p,"avgCost")?:0.0; val qty=p.optInt("qty"); val avg=d33(p,"avgCost")?:0.0; val ret=if(avg>0)(px/avg-1)*100 else 0.0; val cw=if(nav>0)qty*px/nav*100 else 0.0; val tw=(tmap[c]?.weight?:0.0)*100
                    Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically){Column(Modifier.weight(1f)){Text("${p.optString("name",c)} $c",fontWeight=FontWeight.SemiBold,fontSize=10.sp);Text("${qty}股 · 当前${String.format("%.1f%%",cw)} / 目标${String.format("%.1f%%",tw)}",color=P33Muted,fontSize=8.sp)};Text(pct33(ret),color=if(ret>=0)P33Red else P33Green,fontSize=10.sp,fontWeight=FontWeight.Bold)}
                }
            }
            val dec=state.optJSONArray("decisions")?:JSONArray()
            if(dec.length()>0){ HorizontalDivider(); Text("最近模拟动作",fontWeight=FontWeight.Bold,fontSize=11.sp); for(i in dec.length()-1 downTo maxOf(0,dec.length()-6)){val x=dec.optJSONObject(i)?:continue;Text("${x.optString("side")} ${x.optString("name")} ${if(x.optInt("qty")>0)"${x.optInt("qty")}股" else ""} · ${x.optString("text")}",fontSize=8.sp,color=P33Muted)} }
            Text("说明：全部成交均为本机影子模拟；资金调整不计策略收益，普通A股模拟卖出遵守T+1。该账户只用于积累样本外证据。",fontSize=8.sp,color=P33Muted)
        }
    }
}

@Composable private fun PMetric33(label:String,value:String,color:Color,modifier:Modifier=Modifier){Column(modifier){Text(label,color=P33Muted,fontSize=8.sp);Text(value,color=color,fontWeight=FontWeight.Bold,fontSize=11.sp)}}
