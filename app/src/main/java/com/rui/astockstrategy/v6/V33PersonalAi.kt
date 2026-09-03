package com.rui.astockstrategy.v6

import android.content.Context
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
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
import java.time.DayOfWeek
import java.time.LocalTime
import java.time.ZoneId
import java.time.ZonedDateTime
import kotlin.math.abs

private const val P33_URL = "https://raw.githubusercontent.com/cskjin940509-ops/cskjin/main/astock_ai_portfolio/latest.json"
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
private fun fee33(amount: Double, sell: Boolean): Double = maxOf(5.0, amount * 0.0002) + amount * 0.0000541 + if (sell) amount * 0.0005 else 0.0
private fun px33(v: Double): Double = kotlin.math.round(v * 100.0) / 100.0

private suspend fun fetch33(): JSONObject = withContext(Dispatchers.IO) {
    val c = URL(P33_URL).openConnection() as HttpURLConnection
    c.connectTimeout = 8000; c.readTimeout = 8000
    c.setRequestProperty("User-Agent", "Mozilla/5.0 AStockStrategy/3.3")
    c.setRequestProperty("Cache-Control", "no-cache")
    try {
        c.connect(); if (c.responseCode !in 200..299) error("HTTP ${c.responseCode}")
        JSONObject(c.inputStream.bufferedReader().use { it.readText() })
    } finally { c.disconnect() }
}

private object PersonalStore33 {
    private const val PREF = "ai_personal_dynamic_v33"
    private const val KEY = "state"
    fun load(ctx: Context): JSONObject {
        val raw = ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).getString(KEY, null)
        if (!raw.isNullOrBlank()) runCatching { return JSONObject(raw) }
        return JSONObject().apply {
            put("configuredCapital", 1000000.0); put("cash", 1000000.0); put("realizedPnl", 0.0)
            put("positions", JSONObject()); put("decisions", JSONArray()); put("tradeDate", "")
            put("createdAt", System.currentTimeMillis())
        }
    }
    fun save(ctx: Context, s: JSONObject) { ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit().putString(KEY, s.toString()).apply() }
}

private fun cnNow33(): ZonedDateTime = ZonedDateTime.now(ZoneId.of("Asia/Shanghai"))
private fun trading33(): Boolean {
    val z = cnNow33(); val d = z.dayOfWeek
    if (d == DayOfWeek.SATURDAY || d == DayOfWeek.SUNDAY) return false
    val t = z.toLocalTime()
    return (t >= LocalTime.of(9,30) && t <= LocalTime.of(11,30)) || (t >= LocalTime.of(13,0) && t <= LocalTime.of(15,0))
}
private fun today33(): String = cnNow33().toLocalDate().toString()

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
    val old = d33(s, "configuredCapital") ?: 1000000.0
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

private fun resetT1Day33(s: JSONObject) {
    val today=today33(); if(s.optString("tradeDate")==today) return
    val ps=s.optJSONObject("positions")?:JSONObject(); val it=ps.keys(); while(it.hasNext()){ ps.optJSONObject(it.next())?.put("todayBuyQty",0) }
    s.put("tradeDate",today)
}

private fun rebalance33(ctx: Context, s0: JSONObject, data: JSONObject?): JSONObject {
    val s=JSONObject(s0.toString()); resetT1Day33(s)
    if(!trading33()) { PersonalStore33.save(ctx,s); return s }
    val targets=targets33(data); if(targets.isEmpty()) { PersonalStore33.save(ctx,s); return s }
    val tmap=targets.associateBy{it.code}; val prices=priceMap33(data); val ps=s.optJSONObject("positions")?:JSONObject().also{s.put("positions",it)}
    var nav=nav33(s,prices).coerceAtLeast(1.0)

    // 先卖：目标仓位下降、移出目标组合或缩减资金后现金为负。
    val codes=mutableListOf<String>(); val it=ps.keys(); while(it.hasNext()) codes+=it.next()
    for(c in codes){
        val p=ps.optJSONObject(c)?:continue; val qty=p.optInt("qty"); if(qty<=0) continue
        val px=prices[c]?:d33(p,"avgCost")?:continue; val tw=tmap[c]?.weight?:0.0; val cw=qty*px/nav; val cash=d33(s,"cash")?:0.0
        val need = tw==0.0 || cw-tw>=0.018 || cash<0
        if(!need) continue
        val targetValue=nav*tw; var sellValue=maxOf(0.0,qty*px-targetValue); if(cash<0) sellValue=maxOf(sellValue,-cash)
        var sq=(sellValue/px/100.0).toInt()*100; if(tw==0.0) sq=qty
        val sellable=maxOf(0,qty-p.optInt("todayBuyQty")); sq=minOf(sq,sellable); sq=(sq/100)*100
        if(sq<=0 || (sq*px<5000 && tw>0)) continue
        val ex=px33(px*0.9995); val amount=ex*sq; val fee=fee33(amount,true); val avg=d33(p,"avgCost")?:px
        s.put("cash",(d33(s,"cash")?:0.0)+amount-fee); s.put("realizedPnl",(d33(s,"realizedPnl")?:0.0)+(ex-avg)*sq-fee)
        val remain=qty-sq
        if(remain<=0) ps.remove(c) else { p.put("qty",remain); p.put("costAmount",avg*remain) }
        appendDecision33(s,if(remain<=0)"卖出" else "减仓",p.optString("name",c),c,sq,ex,if(tw==0.0)"影子目标仓位降为0" else "模拟仓位高于影子目标，执行再平衡")
        nav=nav33(s,prices).coerceAtLeast(1.0)
    }

    // 再买：不限制持股数量，也不限制当天新买次数；现金与目标权重决定是否成交。
    for(t in targets){
        val px=t.price; nav=nav33(s,prices).coerceAtLeast(1.0); val p=ps.optJSONObject(t.code); val qty=p?.optInt("qty")?:0; val cw=qty*px/nav; val delta=t.weight-cw
        if(delta<0.018) continue
        val cash=d33(s,"cash")?:0.0; if(cash<100.0*px) continue
        val budget=minOf(delta*nav,cash*0.98); var bq=(budget/(px*1.0005)/100.0).toInt()*100; if(bq<100) continue
        val ex=px33(px*1.0005); var amount=ex*bq; var fee=fee33(amount,false)
        while(bq>=100 && amount+fee>cash){ bq-=100; amount=ex*bq; fee=if(bq>0)fee33(amount,false)else 0.0 }
        if(bq<100) continue
        if(p==null){
            ps.put(t.code,JSONObject().apply{put("code",t.code);put("name",t.name);put("sector",t.sector);put("qty",bq);put("avgCost",(amount+fee)/bq);put("costAmount",amount+fee);put("todayBuyQty",bq);put("entryDate",today33())})
        } else {
            val oq=p.optInt("qty"); val oc=d33(p,"costAmount")?:((d33(p,"avgCost")?:px)*oq); val nq=oq+bq; val nc=oc+amount+fee
            p.put("qty",nq);p.put("costAmount",nc);p.put("avgCost",nc/nq);p.put("todayBuyQty",p.optInt("todayBuyQty")+bq)
        }
        s.put("cash",cash-amount-fee); appendDecision33(s,if(qty>0)"加仓" else "买入",t.name,t.code,bq,ex,"影子目标仓位${String.format("%.1f%%",t.weight*100)}；旧模型参考分${String.format("%.0f",t.score)}")
    }
    PersonalStore33.save(ctx,s); return s
}

@Composable
fun PersonalAiPanel33() {
    val ctx=LocalContext.current
    var state by remember { mutableStateOf(PersonalStore33.load(ctx)) }
    var data by remember { mutableStateOf<JSONObject?>(null) }
    var capitalText by remember { mutableStateOf(String.format("%.0f",d33(state,"configuredCapital")?:1000000.0)) }
    var status by remember { mutableStateOf("等待影子目标组合") }

    LaunchedEffect(Unit){
        while(true){
            runCatching{fetch33()}.onSuccess{ d-> data=d; state=rebalance33(ctx,state,d); status="已按最新目标完成模拟再平衡检查" }.onFailure{status="影子目标组合暂未同步"}
            delay(30000)
        }
    }
    val prices=priceMap33(data); val nav=nav33(state,prices); val capital=d33(state,"configuredCapital")?:1000000.0; val cash=d33(state,"cash")?:0.0; val pnl=nav-capital
    val pos=state.optJSONObject("positions")?:JSONObject(); val targets=targets33(data); val tmap=targets.associateBy{it.code}; val positionPct=if(nav>0)(nav-cash)/nav*100 else 0.0

    Card(shape=RoundedCornerShape(18.dp),colors=CardDefaults.cardColors(containerColor=Color.White)){
        Column(Modifier.fillMaxWidth().padding(14.dp),verticalArrangement=Arrangement.spacedBy(8.dp)){
            Text("个人影子组合（模拟）",fontWeight=FontWeight.Bold,fontSize=17.sp)
            Text("只在本机模拟持仓与费用 · 不连接券商 · 不会发送真实订单",color=P33Muted,fontSize=9.sp)
            Row(horizontalArrangement=Arrangement.spacedBy(8.dp),verticalAlignment=Alignment.CenterVertically){
                OutlinedTextField(value=capitalText,onValueChange={capitalText=it.filter{ch->ch.isDigit()||ch=='.'}},label={Text("投入本金（元）")},singleLine=true,modifier=Modifier.weight(1f))
                Button(onClick={ val v=capitalText.toDoubleOrNull(); if(v!=null&&v>=10000){state=applyCapital33(state,v); if(trading33()) state=rebalance33(ctx,state,data); PersonalStore33.save(ctx,state); status=if(trading33())"模拟本金已调整，并已检查影子目标" else "模拟本金已调整，下个交易时段再检查"} }){Text("应用")}
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
