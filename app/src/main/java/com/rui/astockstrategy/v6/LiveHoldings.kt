package com.rui.astockstrategy.v6
import org.json.JSONArray
import org.json.JSONObject
import java.time.*
import java.time.format.DateTimeFormatter

/** Display only: never modifies trades, cash, quantities or strategy. */
object LiveHoldings {
    private val zone = ZoneId.of("Asia/Shanghai")
    fun stamp(v: String?): Instant? = runCatching { Instant.parse(v) }.getOrNull()
        ?: runCatching { OffsetDateTime.parse(v).toInstant() }.getOrNull()
        ?: runCatching { LocalDateTime.parse(v, DateTimeFormatter.ofPattern("yyyyMMddHHmmss")).atZone(zone).toInstant() }.getOrNull()
    fun trading(now: Instant): Boolean {
        val z=now.atZone(zone); val t=z.toLocalTime()
        return z.dayOfWeek.value<=5 && ((t>=LocalTime.of(9,30)&&t<LocalTime.of(11,30))||(t>=LocalTime.of(13,0)&&t<LocalTime.of(15,0)))
    }
    fun usable(q: Quote, now: Instant): Boolean {
        val at=stamp(q.quoteTimestamp) ?: return false
        if(q.price?.let { it.isFinite()&&it>0 }!=true || at>now) return false
        val z=now.atZone(zone); val a=at.atZone(zone)
        if(z.toLocalDate()!=a.toLocalDate()) return false
        if(trading(now)) return Duration.between(at,now).seconds<=20
        val t=z.toLocalTime(); val qt=a.toLocalTime()
        return (t>=LocalTime.of(15,0)&&qt>=LocalTime.of(15,0)) || (t>=LocalTime.of(11,30)&&t<LocalTime.of(13,0)&&qt>=LocalTime.of(11,29))
    }
    fun merge(old: Map<String,Quote>, incoming: Map<String,Quote>, now: Instant): Map<String,Quote> = old.toMutableMap().apply {
        incoming.forEach { (k,q) ->
            val at=stamp(q.quoteTimestamp); val before=stamp(get(k)?.quoteTimestamp)
            if(at!=null&&at<=now&&q.price?.let { it.isFinite()&&it>0 }==true&&(before==null||at>before)) put(k,q)
        }
    }
    data class View(val positions: JSONArray,val summary: JSONObject?,val covered: Int,val total: Int,val oldest: Instant?)
    fun value(snapshot: JSONObject?,quotes: Map<String,Quote>,report: JSONObject?,now: Instant): View {
        val rows=snapshot?.optJSONArray("positions")?:JSONArray(); val out=JSONArray()
        var covered=0; var oldest:Instant?=null; var market=0.0; var cost=0.0
        val today=now.atZone(zone).toLocalDate().toString()
        for(i in 0 until rows.length()) {
            val row=JSONObject(rows.getJSONObject(i).toString()); val q=quotes[symbol(row.optString("code"))]
            val at=stamp(q?.quoteTimestamp)
            val baseline=stamp(row.optString("valuationQuoteAt"))?:stamp(snapshot?.optString("updatedAt"))
            val current=q!=null&&usable(q,now)&&at!=null&&baseline!=null&&(at>=baseline||(!trading(now)&&baseline.atZone(zone).toLocalDate().toString()==today))
            row.put("displayQuoteAt",JSONObject.NULL).put("marketChangePct",JSONObject.NULL)
            if(current) {
                covered++; if(oldest==null||at!!<oldest) oldest=at
                val price=q!!.price!!; val qty=row.optInt("qty"); val avg=row.optDouble("avgCost",Double.NaN)
                row.put("currentPrice",price).put("marketValue",price*qty).put("displayQuoteAt",at.toString())
                q.prev?.takeIf { it.isFinite()&&it>0 }?.let { row.put("marketChangePct",(price/it-1)*100) }
                if(avg.isFinite()&&avg>0) row.put("floatingPnl",(price-avg)*qty).put("floatingReturnPct",(price/avg-1)*100)
            }
            market+=row.optDouble("marketValue",Double.NaN); cost+=row.optInt("qty")*row.optDouble("avgCost",Double.NaN); out.put(row)
        }
        val summary=snapshot?.optJSONObject("summary")?.let { JSONObject(it.toString()) }
        if(summary!=null) {
            val m=summary.optDouble("marketValue",Double.NaN); val p=summary.optDouble("floatingPnl",Double.NaN)
            if(m.isFinite()&&p.isFinite()&&m-p>0) summary.put("holdingReturnPct",p/(m-p)*100)
        }
        if(summary!=null&&rows.length()>0&&covered==rows.length()&&market.isFinite()&&cost.isFinite()) {
            val cash=summary.optDouble("cash",Double.NaN); val assets=cash+market
            if(cash.isFinite()&&assets>0) {
                summary.put("totalAssets",assets).put("marketValue",market).put("floatingPnl",market-cost).put("positionPct",market/assets*100)
                    .put("holdingReturnPct",if(cost>0)(market-cost)/cost*100 else JSONObject.NULL)
                for(i in 0 until out.length()) out.getJSONObject(i).put("currentWeightPct",out.getJSONObject(i).optDouble("marketValue")/assets*100)
                val daily=report?.optJSONArray("rows")
                val prior=(0 until (daily?.length()?:0)).mapNotNull { daily?.optJSONObject(it) }.filter { it.optString("date")<today }.maxByOrNull { it.optString("date") }
                val denominator=prior?.optDouble("closeAssets",Double.NaN)?:Double.NaN
                val events=snapshot?.optJSONArray("capitalEvents"); var flow=0.0
                for(i in 0 until (events?.length()?:0)) {
                    val e=events?.optJSONObject(i)?:continue
                    if(e.optString("timestamp").take(10)==today) flow+=e.optDouble("cashContribution",0.0)
                }
                if(denominator.isFinite()&&denominator>0&&snapshot?.optString("updatedAt")?.take(10)==today&&report?.optString("generatedAt")?.take(10)==today&&report.optBoolean("ledgerReconciled")) {
                    summary.put("todayPnl",assets-denominator-flow).put("todayReturnPct",(assets-denominator-flow)/denominator*100)
                } else summary.put("todayPnl",JSONObject.NULL).put("todayReturnPct",JSONObject.NULL)
            }
        }
        return View(out,summary,covered,rows.length(),oldest)
    }
}
