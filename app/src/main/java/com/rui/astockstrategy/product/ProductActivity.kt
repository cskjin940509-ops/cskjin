package com.rui.astockstrategy.product

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
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
import kotlin.math.abs

private val Navy=Color(0xFF10243E); private val Blue=Color(0xFF1D5FD1)
private val Green=Color(0xFF087F5B); private val Red=Color(0xFFC43D3D)
private val Amber=Color(0xFF9A5B00); private val Ink=Color(0xFF172033)
private val Muted=Color(0xFF667085); private val Canvas=Color(0xFFF3F6FA)
private val SoftBlue=Color(0xFFEAF1FF); private val SoftGreen=Color(0xFFE7F6F0); private val SoftAmber=Color(0xFFFFF3DD)

private data class Candidate(val rank:Int,val code:String,val name:String,val sector:String?,val score:Double?,val close:Double?,val limit:Double?,val status:String,val reason:String,val gaps:List<String>)
private data class Holding(val code:String,val name:String,val sector:String?,val qty:Int,val cost:Double?,val price:Double?,val ret:Double?,val weight:Double?,val stop:Double?,val action:String,val reason:String)
private data class Decision(val time:String,val side:String,val code:String,val name:String,val qty:Int,val price:Double?,val pnl:Double?,val reason:String)
private data class Snap(
    val updated:String,val version:String,val mode:String,val simulated:Boolean,
    val assets:Double,val cash:Double,val mv:Double,val posPct:Double,val dayRet:Double?,val allRet:Double?,val mdd:Double?,val posCount:Int,
    val marketState:String,val cap:Double?,val allowNew:Boolean,val marketReason:String,
    val batchCount:Int,val activeBatches:Int,val pendingBuy:Int,val pendingSell:Int,val signalDate:String?,
    val candidates:List<Candidate>,val holdings:List<Holding>,val decisions:List<Decision>,val rules:Map<String,String>
)

class ProductActivity:ComponentActivity(){override fun onCreate(b:Bundle?){super.onCreate(b);setContent{ProductApp()}}}
private enum class Tab(val zh:String,val icon:ImageVector){HOME("总览",Icons.Default.Home),CANDIDATE("候选",Icons.Default.Checklist),BATCH("批次",Icons.Default.Layers),HOLDING("持仓",Icons.Default.AccountBalanceWallet),RULE("策略",Icons.Default.Rule)}

@OptIn(ExperimentalMaterial3Api::class)
@Composable private fun ProductApp(){
    var tab by remember{mutableStateOf(Tab.HOME)};var data by remember{mutableStateOf<Snap?>(null)};var err by remember{mutableStateOf<String?>(null)};var busy by remember{mutableStateOf(true)}
    LaunchedEffect(Unit){while(true){busy=true;runCatching{Api.fetch()}.onSuccess{data=it;err=null}.onFailure{err=it.javaClass.simpleName};busy=false;delay(30_000)}}
    MaterialTheme(colorScheme=lightColorScheme(primary=Blue,background=Canvas,surface=Color.White)){
        Scaffold(containerColor=Canvas,topBar={TopAppBar(colors=TopAppBarDefaults.topAppBarColors(containerColor=Navy,titleContentColor=Color.White),title={Column{Text("A股筛选池",fontWeight=FontWeight.Bold);Text("原选股策略 · T+1八批轮动",fontSize=11.sp,color=Color(0xFFBFD0EA))}},actions={Pill(if(busy)"同步中" else if(err==null)"数据已同步" else "同步异常",err==null);Spacer(Modifier.width(10.dp))})},bottomBar={NavigationBar{Tab.entries.forEach{t->NavigationBarItem(selected=tab==t,onClick={tab=t},icon={Icon(t.icon,null)},label={Text(t.zh,fontSize=10.sp)})}}}){pad->
            Box(Modifier.padding(pad).fillMaxSize()){val s=data;if(s==null) Loading(err) else when(tab){Tab.HOME->Home(s,err);Tab.CANDIDATE->Candidates(s);Tab.BATCH->Batches(s);Tab.HOLDING->Holdings(s);Tab.RULE->Rules(s)}}
        }
    }
}

@Composable private fun Home(s:Snap,err:String?){Page{
    item{Hero{Row(verticalAlignment=Alignment.CenterVertically){Column(Modifier.weight(1f)){Text("模拟组合总资产",color=Color(0xFFBFD0EA),fontSize=11.sp);Text(money(s.assets),color=Color.White,fontSize=28.sp,fontWeight=FontWeight.Bold);Text("仓位 ${pct(s.posPct)} · 现金 ${money(s.cash)}",color=Color(0xFFD8E3F3),fontSize=11.sp)};Column(horizontalAlignment=Alignment.End){Metric("今日",s.dayRet);Metric("累计",s.allRet)}}}}
    err?.let{item{Notice("本轮同步异常：$it。保留上次成功快照，不把缓存冒充实时数据。",SoftAmber)}}
    item{Title("执行状态")};item{CardBox{KV("市场状态",stateZh(s.marketState));KV("市场仓位上限",s.cap?.let{pct(it*100)}?:"待确认");KV("是否允许新仓",if(s.allowNew)"允许，仍须通过成交约束" else "暂停新增");KV("有效批次","${s.activeBatches}/8");KV("待买入 / 待卖出","${s.pendingBuy} / ${s.pendingSell}");HorizontalDivider(Modifier.padding(vertical=8.dp));Text(s.marketReason,fontSize=11.sp,color=Muted,lineHeight=16.sp)}}
    item{Title("从选股到成交")};item{CardBox{Step("1","T日选股","原板块、资金、量价评分与候选排序",true);Step("2","收盘冻结",s.signalDate?.let{"$it 已冻结 ${s.pendingBuy}只"}?:"等待有效收盘候选",s.signalDate!=null);Step("3","T+1买入","98%限价优先；未触及则收盘窗口兜底",false);Step("4","八批轮动","第9个有效批次形成后轮出最老批次",false)}}
    item{Title("组合风险")};item{Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){Mini("持仓","${s.posCount}只",Modifier.weight(1f));Mini("市值",money(s.mv),Modifier.weight(1f));Mini("最大回撤",s.mdd?.let(::pct)?:"—",Modifier.weight(1f))}}
    item{Notice("更新时间 ${short(s.updated)}。仅为模拟交易，不连接券商，不构成收益承诺。",SoftBlue)}
}}

@Composable private fun Candidates(s:Snap){Page{
    item{Title("T+1执行候选")};item{Notice("名单在T日收盘冻结；排名决定批内分配。真实成交还要检查市场上限、行情新鲜度、涨停、成交容量、现金及单股/板块上限。",SoftBlue)}
    item{Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){Mini("信号日",s.signalDate?:"—",Modifier.weight(1f));Mini("待执行","${s.pendingBuy}只",Modifier.weight(1f));Mini("单股上限","2.25%",Modifier.weight(1f))}}
    if(s.candidates.isEmpty())item{Empty("当前没有已冻结候选")} else items(s.candidates,key={it.code}){c->CardBox{Row(verticalAlignment=Alignment.CenterVertically){Surface(color=Navy,shape=RoundedCornerShape(10.dp)){Text("${c.rank}",Modifier.padding(horizontal=10.dp,vertical=7.dp),color=Color.White,fontWeight=FontWeight.Bold)};Spacer(Modifier.width(10.dp));Column(Modifier.weight(1f)){Text("${c.name}  ${c.code}",fontWeight=FontWeight.Bold);Text(c.sector?:"板块待同步",color=Muted,fontSize=10.sp)};Tag(statusZh(c.status),true)};Spacer(Modifier.height(10.dp));Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){Val("信号收盘",c.close?.let(::price)?:"—",Modifier.weight(1f));Val("98%限价",c.limit?.let(::price)?:"—",Modifier.weight(1f));Val("评分",c.score?.let{String.format("%.1f",it)}?:"—",Modifier.weight(1f))};Text(c.reason,fontSize=11.sp,color=Muted,modifier=Modifier.padding(top=8.dp),lineHeight=16.sp);if(c.gaps.isNotEmpty())Text("降级项：${c.gaps.take(3).joinToString("；")}",fontSize=10.sp,color=Amber)}}
    }
}

@Composable private fun Batches(s:Snap){Page{
    item{Title("八批资金账本")};item{Hero{Text("每个有效收盘信号 = 1个独立批次",color=Color.White,fontWeight=FontWeight.Bold,fontSize=16.sp);Text("每批预算为信号日收盘总资产的1/8（约12.5%）",color=Color(0xFFD8E3F3),fontSize=12.sp,modifier=Modifier.padding(vertical=8.dp));LinearProgressIndicator({(s.activeBatches/8f).coerceIn(0f,1f)},Modifier.fillMaxWidth().height(8.dp),color=Color(0xFF61D6A5),trackColor=Color(0xFF314863));Text("当前 ${s.activeBatches}/8批 · 历史共${s.batchCount}批",color=Color.White,fontSize=11.sp,modifier=Modifier.padding(top=7.dp))}}
    item{Title("批次生命周期")};item{CardBox{RuleLine("建批","T日收盘冻结候选、排名、收盘价和批次预算");RuleLine("开盘成交","T+1开盘价≤98%限价，按开盘价成交");RuleLine("日内触发","最低价触及98%限价，按限价成交");RuleLine("收盘兜底","未触及则14:45–14:55按有效行情买入");RuleLine("涨停顺延","一字涨停最多顺延3个有效交易日");RuleLine("FIFO轮出","第9批形成后，T+1开盘卖出最老批次");RuleLine("资金回流","卖出资金只补充最新信号池")}}
    item{Title("成交硬约束")};item{CardBox{KV("批次预算","总资产 × 12.5%");KV("单股上限","净值 × 2.25%");KV("板块上限","净值 × 30%");KV("最小订单","10,000元，100股整手");KV("当前待退出","${s.pendingSell}笔")}}
}}

@Composable private fun Holdings(s:Snap){Page{
    item{Title("当前模拟持仓")};item{Notice("旧持仓与历史账本不回写；新策略仅影响生效后的订单。ATR止损和组合风险退出优先于批次轮动。",SoftAmber)}
    if(s.holdings.isEmpty())item{Empty("当前无持仓")} else items(s.holdings,key={it.code}){h->CardBox{Row{Column(Modifier.weight(1f)){Text("${h.name}  ${h.code}",fontWeight=FontWeight.Bold);Text("${h.sector?:"—"} · ${h.qty}股 · 权重${h.weight?.let(::pct)?:"—"}",fontSize=10.sp,color=Muted)};Text(h.ret?.let(::signedPct)?:"—",color=gain(h.ret),fontWeight=FontWeight.Bold)};Spacer(Modifier.height(8.dp));Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){Val("成本",h.cost?.let(::price)?:"—",Modifier.weight(1f));Val("现价",h.price?.let(::price)?:"—",Modifier.weight(1f));Val("硬止损",h.stop?.let(::price)?:"—",Modifier.weight(1f))};Text("当前动作：${h.action}",fontWeight=FontWeight.SemiBold,color=Blue,fontSize=11.sp,modifier=Modifier.padding(top=8.dp));Text(h.reason,color=Muted,fontSize=10.sp,lineHeight=15.sp)}}
    item{Title("最近成交")};if(s.decisions.isEmpty())item{Empty("暂无成交记录")} else items(s.decisions.take(20)){d->CardBox{Row{Tag(d.side,d.side=="买入");Spacer(Modifier.width(8.dp));Column(Modifier.weight(1f)){Text("${d.name} ${d.code}",fontWeight=FontWeight.Bold);Text("${d.qty}股 × ${d.price?.let(::price)?:"—"} · ${short(d.time)}",fontSize=10.sp,color=Muted)};d.pnl?.let{Text(money(it),color=gain(it),fontWeight=FontWeight.Bold,fontSize=11.sp)}};Text(d.reason,fontSize=10.sp,color=Muted,modifier=Modifier.padding(top=7.dp))}}
}}

@Composable private fun Rules(s:Snap){Page{
    item{Title("产品策略说明")};item{Notice("选股层不变，执行层为T+1八批轮动。“允许买入”不等于无条件成交，必须同时通过成交与风控约束。",SoftBlue)}
    item{RuleGroup("选股策略",s.rules["newEntry"]?:"沿用原板块、资金、量价规则筛选并排序。")};item{RuleGroup("仓位与轮动",s.rules["position"]?:"八批轮动，每批12.5%。")};item{RuleGroup("买入执行",s.rules["rebalance"]?:"T+1按98%限价或收盘窗口执行。")};item{RuleGroup("卖出规则",s.rules["exit"]?:"第9批轮出最老批次，保护性退出优先。")};item{RuleGroup("ATR止损",s.rules["stop"]?:"风险线只收紧，不放宽。")};item{RuleGroup("组合风控",s.rules["risk"]?:"当日亏损与日终回撤触发停买或降仓。")}
    item{Title("风险触发表")};item{CardBox{RuleLine("当日≤-1.5%","停止新增买入");RuleLine("当日≤-2.5%","总仓位目标降低25%");RuleLine("回撤≤-5%","仓位上限减半");RuleLine("回撤≤-8%","暂停新仓至少5个真实交易日");RuleLine("无报价/无容量","不假设成交，保留明确待办");RuleLine("跌停卖不出","顺延，不虚构卖出")}}
    item{Title("版本与审计")};item{CardBox{KV("策略版本",s.version);KV("执行模式",if(s.simulated)"仅模拟，不连接券商" else s.mode);KV("数据更新时间",short(s.updated));Text(s.rules["audit"]?:"新规则不回写旧成交，所有订单保留时点证据。",fontSize=10.sp,color=Muted,modifier=Modifier.padding(top=8.dp))}}
}}

@Composable private fun Page(content:androidx.compose.foundation.lazy.LazyListScope.()->Unit)=LazyColumn(contentPadding=PaddingValues(14.dp),verticalArrangement=Arrangement.spacedBy(10.dp),content=content)
@Composable private fun Hero(content:@Composable ColumnScope.()->Unit)=Card(colors=CardDefaults.cardColors(containerColor=Navy),shape=RoundedCornerShape(20.dp)){Column(Modifier.fillMaxWidth().padding(16.dp),content=content)}
@Composable private fun CardBox(content:@Composable ColumnScope.()->Unit)=Card(colors=CardDefaults.cardColors(containerColor=Color.White),shape=RoundedCornerShape(16.dp)){Column(Modifier.fillMaxWidth().padding(14.dp),content=content)}
@Composable private fun Title(t:String)=Text(t,color=Ink,fontSize=17.sp,fontWeight=FontWeight.Bold)
@Composable private fun Notice(t:String,c:Color)=Surface(color=c,shape=RoundedCornerShape(14.dp)){Text(t,Modifier.fillMaxWidth().padding(12.dp),color=Ink,fontSize=11.sp,lineHeight=16.sp)}
@Composable private fun KV(k:String,v:String)=Row(Modifier.fillMaxWidth().padding(vertical=3.dp)){Text(k,Modifier.weight(1f),color=Muted,fontSize=11.sp);Text(v,color=Ink,fontWeight=FontWeight.SemiBold,fontSize=11.sp)}
@Composable private fun Mini(k:String,v:String,m:Modifier)=Card(m,shape=RoundedCornerShape(14.dp)){Column(Modifier.padding(11.dp)){Text(k,color=Muted,fontSize=9.sp);Text(v,fontWeight=FontWeight.Bold,fontSize=12.sp)}}
@Composable private fun Val(k:String,v:String,m:Modifier)=Column(m.background(Canvas,RoundedCornerShape(10.dp)).padding(8.dp)){Text(k,color=Muted,fontSize=9.sp);Text(v,fontWeight=FontWeight.Bold,fontSize=12.sp)}
@Composable private fun Step(n:String,t:String,b:String,done:Boolean)=Row(Modifier.padding(vertical=7.dp),verticalAlignment=Alignment.Top){Surface(color=if(done)Green else Blue,shape=RoundedCornerShape(20.dp)){Text(n,Modifier.padding(horizontal=9.dp,vertical=5.dp),color=Color.White,fontWeight=FontWeight.Bold,fontSize=10.sp)};Spacer(Modifier.width(10.dp));Column{Text(t,fontWeight=FontWeight.Bold,fontSize=12.sp);Text(b,color=Muted,fontSize=10.sp,lineHeight=14.sp)}}
@Composable private fun RuleLine(t:String,b:String)=Row(Modifier.fillMaxWidth().padding(vertical=5.dp),verticalAlignment=Alignment.Top){Text(t,Modifier.width(92.dp),color=Blue,fontWeight=FontWeight.Bold,fontSize=10.sp);Text(b,Modifier.weight(1f),color=Ink,fontSize=10.sp,lineHeight=15.sp)}
@Composable private fun RuleGroup(t:String,b:String)=CardBox{Text(t,fontWeight=FontWeight.Bold,color=Blue);Text(b,color=Ink,fontSize=11.sp,lineHeight=17.sp,modifier=Modifier.padding(top=7.dp))}
@Composable private fun Tag(t:String,ok:Boolean)=Surface(color=if(ok)SoftGreen else SoftAmber,shape=RoundedCornerShape(20.dp)){Text(t,Modifier.padding(horizontal=9.dp,vertical=5.dp),color=if(ok)Green else Amber,fontSize=9.sp,fontWeight=FontWeight.Bold)}
@Composable private fun Pill(t:String,ok:Boolean)=Surface(color=if(ok)Color(0xFF1D6D56) else Color(0xFF81551C),shape=RoundedCornerShape(20.dp)){Text(t,Modifier.padding(horizontal=9.dp,vertical=5.dp),color=Color.White,fontSize=9.sp)}
@Composable private fun Metric(k:String,v:Double?)=Text("$k ${v?.let(::signedPct)?:"—"}",color=gain(v),fontWeight=FontWeight.Bold,fontSize=12.sp)
@Composable private fun Empty(t:String)=CardBox{Text(t,color=Muted,fontSize=12.sp)}
@Composable private fun Loading(e:String?)=Box(Modifier.fillMaxSize(),contentAlignment=Alignment.Center){Column(horizontalAlignment=Alignment.CenterHorizontally){CircularProgressIndicator();Text(if(e==null)"正在读取策略与交易账本" else "读取失败：$e",Modifier.padding(top=12.dp),color=Muted)}}

private object Api{
    private const val ENDPOINT="https://raw.githubusercontent.com/cskjin940509-ops/cskjin/main/astock_ai_portfolio/latest.json"
    suspend fun fetch():Snap=withContext(Dispatchers.IO){
        val r=JSONObject(get(ENDPOINT));val sm=r.optJSONObject("summary")?:JSONObject();val sel=r.optJSONObject("selection45")?:JSONObject();val market=sel.optJSONObject("market")?:JSONObject();val batch=r.optJSONObject("batchExecutionV6")?:JSONObject()
        val details=mutableMapOf<String,JSONObject>();val ca=sel.optJSONArray("candidates")?:JSONArray();for(i in 0 until ca.length()){val x=ca.optJSONObject(i)?:continue;details[x.optString("code")]=x}
        val oa=batch.optJSONArray("pendingOrders")?:JSONArray();val cs=(0 until oa.length()).mapNotNull{i->val x=oa.optJSONObject(i)?:return@mapNotNull null;val code=x.optString("code");val d=details[code];Candidate(x.optInt("rank",i+1),code,x.optString("name",code),d?.txt("sector"),d.num("rankingScore")?:d.num("score"),d.num("referencePrice"),x.num("limitPrice"),x.optString("status","WAIT_T_PLUS_ONE"),x.optString("reasonZh","等待T+1执行"),d?.strings("missingOptionalEvidence").orEmpty())}
        val pa=r.optJSONArray("positions")?:JSONArray();val hs=(0 until pa.length()).mapNotNull{i->val x=pa.optJSONObject(i)?:return@mapNotNull null;val p=x.optJSONObject("decisionPlan");Holding(x.optString("code"),x.optString("name"),x.txt("sector"),x.optInt("qty"),x.num("avgCost"),x.num("currentPrice"),x.num("floatingReturnPct"),x.num("currentWeightPct"),x.num("hardStopPrice"),x.optString("currentActionZh","持有观察"),p?.optString("reasonZh")?.takeIf{it.isNotBlank()}?:x.optString("invalidationZh","按风险与批次规则管理"))}
        val da=r.optJSONArray("recentDecisions")?:JSONArray();val ds=(0 until da.length()).mapNotNull{i->val x=da.optJSONObject(i)?:return@mapNotNull null;Decision(x.optString("timestamp"),x.optString("sideZh",x.optString("side")),x.optString("code"),x.optString("name"),x.optInt("qty"),x.num("price"),x.num("realizedPnl"),x.optString("reasonZh"))}
        val ro=r.optJSONObject("rulesZh")?:JSONObject();val rules=ro.keys().asSequence().associateWith{ro.optString(it)}
        Snap(r.optString("updatedAt"),r.optString("strategyVersion"),r.optString("mode"),r.optBoolean("simulated",true),sm.optDouble("totalAssets"),sm.optDouble("cash"),sm.optDouble("marketValue"),sm.optDouble("positionPct"),sm.num("todayReturnPct"),sm.num("cumulativeReturnPct"),sm.num("maxDrawdownPct"),sm.optInt("positionCount"),market.optString("state","UNKNOWN"),market.num("cap"),market.optBoolean("allowNew"),market.optString("reasonZh","等待市场风险证据"),batch.optInt("batchCount"),batch.optInt("activeBatchCount"),batch.optInt("pendingOrderCount"),batch.optInt("pendingExitCount"),batch.txt("lastSignalDate"),cs,hs,ds,rules)
    }
    private fun get(u:String):String{val c=URL(u).openConnection() as HttpURLConnection;c.connectTimeout=10000;c.readTimeout=10000;c.setRequestProperty("User-Agent","AStockPool/4.0 Android");c.setRequestProperty("Cache-Control","no-cache");try{if(c.responseCode !in 200..299)error("HTTP ${c.responseCode}");return c.inputStream.bufferedReader().use{it.readText()}}finally{c.disconnect()}}
}
private fun JSONObject?.num(k:String):Double?=if(this==null||!has(k)||isNull(k))null else opt(k).toString().toDoubleOrNull()
private fun JSONObject.txt(k:String):String?=optString(k).takeIf{it.isNotBlank()&&it!="null"}
private fun JSONObject.strings(k:String):List<String>{val a=optJSONArray(k)?:return emptyList();return(0 until a.length()).mapNotNull{a.optString(it).takeIf(String::isNotBlank)}}
private fun money(v:Double)=when{abs(v)>=1e8->String.format("%.2f亿",v/1e8);abs(v)>=1e4->String.format("%.2f万",v/1e4);else->String.format("%.2f",v)}
private fun pct(v:Double)=String.format("%.2f%%",v);private fun signedPct(v:Double)=String.format("%+.2f%%",v);private fun price(v:Double)=String.format("%.2f",v);private fun short(v:String)=v.replace('T',' ').take(19).ifBlank{"—"}
private fun gain(v:Double?)=when{v==null->Muted;v>=0->Red;else->Green}
private fun stateZh(v:String)=when(v){"BASELINE"->"基准/中性";"DEFENSIVE"->"防守";"RISK_ON"->"积极";"UNKNOWN"->"证据待确认";else->v}
private fun statusZh(v:String)=when(v){"WAIT_T_PLUS_ONE"->"等待T+1";"WAIT_LIMIT_PRICE"->"等待限价";"WAIT_LIMIT_UP_RELEASE"->"涨停顺延";"WAIT_FRESH_QUOTE"->"等待新行情";"WAIT_BUDGET"->"等待额度";"PARTIAL_WAIT"->"部分成交";else->v}
