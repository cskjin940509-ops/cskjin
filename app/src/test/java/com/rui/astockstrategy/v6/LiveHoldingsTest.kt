package com.rui.astockstrategy.v6
import org.junit.Assert.*
import org.junit.Test
import org.json.JSONObject
import java.time.Instant
class LiveHoldingsTest {
    private val now=Instant.parse("2026-09-07T02:00:10Z")
    private fun quote(price:Double=12.0,at:String="20260907100009")=Quote("sh600001","测试","600001",price,10.0,null,null,null,null,"10:00:09",at)
    private fun snapshot()=JSONObject("""{"updatedAt":"2026-09-07T09:59:00+08:00","positions":[{"code":"600001","qty":100,"avgCost":8,"currentPrice":10,"marketValue":1000,"floatingPnl":200}],"summary":{"cash":1000,"totalAssets":2000,"marketValue":1000,"floatingPnl":200}}""")
    @Test fun marksSeparateTodayFromHoldingAndNeverMutateBook() {
        val s=snapshot(); val before=s.toString(); val v=LiveHoldings.value(s,mapOf("sh600001" to quote()),null,now)
        assertEquals(20.0,v.positions.getJSONObject(0).getDouble("marketChangePct"),.001)
        assertEquals(50.0,v.positions.getJSONObject(0).getDouble("floatingReturnPct"),.001)
        assertEquals(2200.0,v.summary!!.getDouble("totalAssets"),.001)
        assertEquals(before,s.toString()); assertTrue(v.summary!!.isNull("todayReturnPct"))
    }
    @Test fun oldFutureAndInvalidPricesAreRejected() {
        assertFalse(LiveHoldings.usable(quote(at="20260904100009"),now))
        assertFalse(LiveHoldings.usable(quote(at="20260907100030"),now))
        assertFalse(LiveHoldings.usable(quote(price=Double.NaN),now))
        val old=mapOf("sh600001" to quote())
        assertEquals(old,LiveHoldings.merge(old,mapOf("sh600001" to quote(9.0,"20260907100001")),now))
    }
    @Test fun partialCoverageKeepsAggregateSnapshot() {
        val s=snapshot(); s.getJSONArray("positions").put(JSONObject("""{"code":"600002","qty":100,"avgCost":8,"marketValue":1000}"""))
        val v=LiveHoldings.value(s,mapOf("sh600001" to quote()),null,now)
        assertEquals(1,v.covered); assertEquals(2000.0,v.summary!!.getDouble("totalAssets"),.001)
    }
    @Test fun dailyReturnUsesPreviousCloseAssets() {
        val report=JSONObject("""{"generatedAt":"2026-09-07T10:00:00+08:00","ledgerReconciled":true,"rows":[{"date":"2026-09-04","closeAssets":2100}]}""")
        val v=LiveHoldings.value(snapshot(),mapOf("sh600001" to quote()),report,now)
        assertEquals(100.0,v.summary!!.getDouble("todayPnl"),.001)
        assertEquals(100.0/2100*100,v.summary!!.getDouble("todayReturnPct"),.001)
    }
    @Test fun newerAccountCannotUseOlderTick() {
        val s=snapshot().put("updatedAt","2026-09-07T10:00:10+08:00")
        assertEquals(0,LiveHoldings.value(s,mapOf("sh600001" to quote()),null,now).covered)
    }
}
