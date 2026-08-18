package com.rui.astockstrategy

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
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
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.nio.charset.Charset
import java.text.DecimalFormat

private val BG=Color(0xFFF6F7FB); private val INK=Color(0xFF171A22); private val MUTED=Color(0xFF707788)
private val BLUE=Color(0xFF3557D4); private val UP=Color(0xFFD84343); private val DOWN=Color(0xFF15966A); private val AMBER=Color(0xFFAE6A00)

data class Stock(val code:String,val name:String,val line:String,val rs:Int,val pools:Set<String>,val reason:String)
data class Sector(val name:String,val rs:Int,val breadth:Int,val status:String)
data class Quote(val symbol:String,val name:String,val code:String,val price:Double?,val prev:Double?,val change:Double?,val high:Double?,val low:Double?,val amount:Double?,val time:String?)
data class Board(val code:String,val name:String,val change:Double?,val amount:Double?,val flow:Double?,val flowPct:Double?,val up:Int,val down:Int,val flat:Int,val members:List<Member>)
data class Member(val code:String,val name:String,val price:Double?,val change:Double?,val amount:Double?,val flow:Double?)
data class FundFlow(val time:String,val main:Double?,val large:Double?,val superLarge:Double?,val mid:Double?,val small:Double?)

private val stocks=listOf(
 Stock("002371","北方华创","半导体设备",94,setOf("B0","B1","B2","B3","B4"),"平台型半导体设备龙头，五池共同确认"),
 Stock("688012","中微公司","半导体设备",95,setOf("B0","B1","B2","B3","B4"),"设备主线核心，五池共同确认"),
 Stock("300308","中际旭创","CPO/光模块",96,setOf("B0","B1","B2","B3","B4"),"高速光模块核心龙头"),
 Stock("300502","新易盛","CPO/光模块",95,setOf("B0","B1","B2","B3","B4"),"高速光模块核心龙头"),
 Stock("688008","澜起科技","AI芯片/互连",90,setOf("B0","B1","B2","B3","B4"),"AI互连与内存接口交叉暴露"),
 Stock("688072","拓荆科技","半导体设备",88,setOf("B0","B1","B2","B4"),"薄膜沉积设备，ETF+两融增强"),
 Stock("002384","东山精密","AI PCB",86,setOf("B0","B1","B3","B4"),"PCB与光通信链交叉"),
 Stock("688361","中科飞测","量检测设备",84,setOf("B0","B1","B2","B4"),"量检测扩散，基本面背离需观察"),
 Stock("300604","长川科技","半导体测试",83,setOf("B3","B4"),"测试设备扩散"),
 Stock("688981","中芯国际","半导体制造",79,setOf("B1","B2","B4"),"融资+ETF确认")
)
private val sectors=listOf(
 Sector("半导体设备",94,81,"Confirmed"), Sector("CPO/光通信",92,76,"Confirmed"), Sector("AI PCB",87,72,"Confirmed"),
 Sector("先进封装",83,68,"Candidate"), Sector("机器人",74,61,"Candidate"), Sector("创新药",66,55,"Rotation")
)

class MainActivity:ComponentActivity(){override fun onCreate(b:Bundle?){super.onCreate(b);setContent{App()}}}
enum class Tab(val title:String){HOME("首页"),MARKET("行情"),MAINLINE("主线"),POOLS("股票池"),RESEARCH("研究")}

@Composable fun App(){
 var tab by remember{mutableStateOf(Tab.HOME)}; var stock by remember{mutableStateOf<Stock?>(null)}; var sector by remember{mutableStateOf<Sector?>(null)}
 var quotes by remember{mutableStateOf<Map<String,Quote>>(emptyMap())}; var status by remember{mutableStateOf("连接中")}
 val symbols=remember{listOf("sh000001","sz399006","sh000688","sh000300","sh000852")+stocks.map{symbol(it.code)}}
 LaunchedEffect(Unit){while(true){runCatching{Market.fetchQuotes(symbols)}.onSuccess{if(it.isNotEmpty()){quotes=it;status="Live"}}.onFailure{status="Fallback"};delay(5000)}}
 MaterialTheme(colorScheme=lightColorScheme(primary=BLUE,background=BG,surface=Color.White,onSurface=INK)){
  Scaffold(containerColor=BG,topBar={TopAppBar(title={Column{Text("A股主线研究",fontWeight=FontWeight.Bold);Text("2026-08-18 · Preview 盘中",fontSize=11.sp,color=AMBER)}},actions={Text(status,fontSize=11.sp,color=if(status=="Live")DOWN else AMBER,modifier=Modifier.padding(end=12.dp))})},bottomBar={NavigationBar{Tab.entries.forEach{t->NavigationBarItem(selected=tab==t,onClick={tab=t},icon={Icon(icon(t),null)},label={Text(t.title)})}}}}){p->
   Box(Modifier.padding(p).fillMaxSize()){when(tab){Tab.HOME->Home(quotes,{tab=it},{stock=it},{sector=it});Tab.MARKET->MarketScreen(quotes,{stock=it},{sector=it});Tab.MAINLINE->Mainline({sector=it});Tab.POOLS->Pools(quotes){stock=it};Tab.RESEARCH->Research()}}
  }
  stock?.let{StockDetail(it,quotes[symbol(it.code)]){stock=null}}
  sector?.let{SectorDetail(it,{m->sector=null;stock=stocks.firstOrNull{s->s.code==m.code}?:Stock(m.code,m.name,it.name,0,emptySet(),"板块成分股，当前未进入策略冻结池")}){sector=null}}
 }
}
@Composable fun icon(t:Tab)=when(t){Tab.HOME->Icons.Default.Home;Tab.MARKET->Icons.Default.ShowChart;Tab.MAINLINE->Icons.Default.AccountTree;Tab.POOLS->Icons.Default.ViewList;Tab.RESEARCH->Icons.Default.Science}

@Composable fun Home(q:Map<String,Quote>,go:(Tab)->Unit,onStock:(Stock)->Unit,onSector:(Sector)->Unit){LazyColumn(contentPadding=PaddingValues(14.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){
 item{Row(horizontalArrangement=Arrangement.spacedBy(10.dp)){Metric("Regime","震荡上行","模型状态",Modifier.weight(1f));Metric("主线","2 + 1","确认 / 候选",Modifier.weight(1f))}}
 item{CardBlock{Text("公开行情快照",fontWeight=FontWeight.Bold);Spacer(Modifier.height(8.dp));Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Index("上证",q["sh000001"]);Index("创业板",q["sz399006"]);Index("科创50",q["sh000688"])};Text("点击“行情”查看公开市场数据",color=BLUE,fontSize=12.sp,modifier=Modifier.padding(top=10.dp).clickable{go(Tab.MARKET)})}}
 item{Title("主线地图")};items(sectors.take(3)){s->SectorRow(s){onSector(s)}}
 item{Title("B4 Combined")};items(stocks.filter{"B4" in it.pools}.take(6)){s->StockRow(s,q[symbol(s.code)]){onStock(s)}}
}}
@Composable fun MarketScreen(q:Map<String,Quote>,onStock:(Stock)->Unit,onSector:(Sector)->Unit){var mode by remember{mutableStateOf("指数")};LazyColumn(contentPadding=PaddingValues(14.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){
 item{Chips(listOf("指数","板块","个股"),mode){mode=it}}
 when(mode){"指数"->{item{CardBlock{Text("公开指数",fontWeight=FontWeight.Bold);listOf("sh000001" to "上证指数","sz399006" to "创业板指","sh000688" to "科创50","sh000300" to "沪深300","sh000852" to "中证1000").forEach{(k,n)->QuoteLine(n,q[k])}}}};"板块"->items(sectors){SectorRow(it){onSector(it)}};else->items(stocks){StockRow(it,q[symbol(it.code)]){onStock(it)}}}
}}
@Composable fun Mainline(onSector:(Sector)->Unit){LazyColumn(contentPadding=PaddingValues(14.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){item{CardBlock{Text("Mainline Engine（主线引擎）",fontWeight=FontWeight.Bold);Text("行业趋势 + 概念扩散 + RS + Breadth + 资金确认",color=MUTED,fontSize=12.sp)}};items(sectors){SectorRow(it){onSector(it)}}}}
@Composable fun Pools(q:Map<String,Quote>,onStock:(Stock)->Unit){var pool by remember{mutableStateOf("B4")};val list=stocks.filter{pool in it.pools};LazyColumn(contentPadding=PaddingValues(14.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){item{Chips(listOf("B0","B1","B2","B3","B4"),pool){pool=it}};item{CardBlock{Text(poolName(pool),fontWeight=FontWeight.Bold);Text("每日收盘后正式冻结；旧名单永久保留",fontSize=11.sp,color=MUTED)}};items(list){StockRow(it,q[symbol(it.code)]){onStock(it)}}}}
@Composable fun Research(){LazyColumn(contentPadding=PaddingValues(14.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){item{CardBlock{Text("Strategy Scorecard（策略成绩卡）",fontWeight=FontWeight.Bold);Text("1/5/10/20/60D Alpha、胜率、MFE/MAE、统计功效",color=MUTED,fontSize=12.sp)}};items(listOf("B0 Base","B1 Margin","B2 ETF","B3 Main Flow","B4 Combined")){CardBlock{Row{Text(it,Modifier.weight(1f),fontWeight=FontWeight.SemiBold);Text("Too Early",color=AMBER)}}}}}

@Composable fun SectorDetail(s:Sector,onStock:(Member)->Unit,onDismiss:()->Unit){var board by remember(s.name){mutableStateOf<Board?>(null)};var page by remember{mutableStateOf("概览")};var err by remember{mutableStateOf<String?>(null)}
 LaunchedEffect(s.name){runCatching{Market.fetchBoard(s.name)}.onSuccess{board=it;if(it==null)err="未匹配到公开板块"}.onFailure{err="板块接口暂不可用"}}
 AlertDialog(onDismissRequest=onDismiss,confirmButton={TextButton(onClick=onDismiss){Text("关闭")}},title={Column{Text(s.name);Text(board?.change?.let(::pct)?:"读取实时板块…",color=board?.change?.let(::pnl)?:MUTED,fontSize=14.sp)}},text={Column{Chips(listOf("概览","成分","资金","策略"),page){page=it};Spacer(Modifier.height(8.dp));LazyColumn(Modifier.heightIn(max=500.dp),verticalArrangement=Arrangement.spacedBy(7.dp)){err?.let{item{Text(it,color=AMBER,fontSize=12.sp)}};when(page){"概览"->{item{KV("今日涨跌",board?.change?.let(::pct)?:"—")};item{KV("成交额",board?.amount?.let(::money)?:"—")};item{KV("上涨 / 下跌 / 平",board?.let{"${it.up} / ${it.down} / ${it.flat}"}?:"—")};item{KV("模型 RS",s.rs.toString())};item{KV("模型 Breadth","${s.breadth}%")}};"成分"->{val m=board?.members.orEmpty();if(m.isEmpty())item{Text("加载中或暂无数据",color=MUTED)};items(m.take(40)){x->Card(Modifier.fillMaxWidth().clickable{onStock(x)},colors=CardDefaults.cardColors(containerColor=Color(0xFFF8F9FC))){Row(Modifier.padding(10.dp)){Column(Modifier.weight(1f)){Text(x.name,fontWeight=FontWeight.SemiBold);Text(x.code,fontSize=10.sp,color=MUTED)};Column(horizontalAlignment=Alignment.End){Text(x.price?.let{DecimalFormat("0.00").format(it)}?:"—");Text(x.change?.let(::pct)?:"—",color=x.change?.let(::pnl)?:MUTED)}}}}};"资金"->{item{KV("主力净流",board?.flow?.let(::signedMoney)?:"—")};item{KV("主力净流占比",board?.flowPct?.let(::pct)?:"—")};item{Text("公开成交单分类，仅作实验因子，不等同真实机构账户。",fontSize=10.sp,color=MUTED)}};else->{item{KV("主线状态",s.status)};item{KV("RS",s.rs.toString())};item{KV("Breadth","${s.breadth}%")};item{Text("实时行情事实与冻结策略判断分栏显示，实时涨跌不会改写历史结论。",fontSize=10.sp,color=MUTED)}}}}}})
}

@Composable fun StockDetail(s:Stock,q0:Quote?,onDismiss:()->Unit){var q by remember{s.let{mutableStateOf(q0)}};var flow by remember{mutableStateOf<FundFlow?>(null)};var page by remember{mutableStateOf("概览")}
 LaunchedEffect(s.code){if(q==null)runCatching{Market.fetchQuotes(listOf(symbol(s.code)))}.onSuccess{q=it[symbol(s.code)]};runCatching{Market.fetchFlow(s.code)}.onSuccess{flow=it}}
 AlertDialog(onDismissRequest=onDismiss,confirmButton={TextButton(onClick=onDismiss){Text("关闭")}},title={Column{Text("${s.name}  ${s.code}");Row{Text(q?.price?.let{DecimalFormat("0.00").format(it)}?:"—",fontWeight=FontWeight.Bold,fontSize=20.sp);Text("  ${q?.change?.let(::pct)?:""}",color=q?.change?.let(::pnl)?:MUTED)}}},text={Column{Chips(listOf("概览","趋势","资金","策略"),page){page=it};Spacer(Modifier.height(8.dp));LazyColumn(Modifier.heightIn(max=480.dp),verticalArrangement=Arrangement.spacedBy(7.dp)){when(page){"概览"->{item{KV("所属主线",s.line)};item{KV("前收",q?.prev?.let{DecimalFormat("0.00").format(it)}?:"—")};item{KV("日高 / 日低","${q?.high?.let{DecimalFormat("0.00").format(it)}?:"—"} / ${q?.low?.let{DecimalFormat("0.00").format(it)}?:"—"}")};item{KV("成交额",q?.amount?.let(::money)?:"—")}};"趋势"->{item{KV("RS（相对强弱）",if(s.rs>0)s.rs.toString() else "未纳入策略排名")};item{KV("MTA（日/周/月）",if(s.rs>0)"D ✓  W ✓  M ✓" else "仅行情观察")};item{Text("后续接入K线图、MA20D/20W/10M和Time Machine历史收益曲线。",fontSize=10.sp,color=MUTED)}};"资金"->{if(flow==null)item{Text("资金数据加载中或暂不可用",color=MUTED)} else {item{KV("时间",flow!!.time)};item{KV("主力净流",flow!!.main?.let(::signedMoney)?:"—")};item{KV("超大单",flow!!.superLarge?.let(::signedMoney)?:"—")};item{KV("大单",flow!!.large?.let(::signedMoney)?:"—")}};item{Text("主力/大单为C级算法分类数据。两融正式信号按T+1使用。",fontSize=10.sp,color=MUTED)}};else->{item{KV("出现池",if(s.pools.isEmpty())"未入策略池" else s.pools.sorted().joinToString(" / "))};item{KV("状态",if(s.pools.isEmpty())"Market" else "Active")};item{Text("入池逻辑",fontWeight=FontWeight.Bold)};item{Text(s.reason,fontSize=12.sp,color=MUTED)}}}}}})
}

@Composable fun Metric(t:String,v:String,sub:String,m:Modifier=Modifier){Card(m,shape=RoundedCornerShape(16.dp)){Column(Modifier.padding(14.dp)){Text(t,fontSize=11.sp,color=MUTED);Text(v,fontWeight=FontWeight.Bold,fontSize=19.sp);Text(sub,fontSize=10.sp,color=MUTED)}}}
@Composable fun CardBlock(c:@Composable ColumnScope.()->Unit){Card(shape=RoundedCornerShape(16.dp),colors=CardDefaults.cardColors(containerColor=Color.White)){Column(Modifier.fillMaxWidth().padding(14.dp),content=c)}}
@Composable fun Title(t:String){Text(t,fontWeight=FontWeight.Bold,fontSize=17.sp)}
@Composable fun Index(n:String,q:Quote?){Column{Text(n,fontSize=11.sp,color=MUTED);Text(q?.price?.let{DecimalFormat("0.00").format(it)}?:"—",fontWeight=FontWeight.Bold);Text(q?.change?.let(::pct)?:"—",color=q?.change?.let(::pnl)?:MUTED,fontSize=11.sp)}}
@Composable fun QuoteLine(n:String,q:Quote?){Row(Modifier.fillMaxWidth().padding(vertical=7.dp)){Text(n,Modifier.weight(1f));Text(q?.price?.let{DecimalFormat("0.00").format(it)}?:"—",fontWeight=FontWeight.SemiBold);Spacer(Modifier.width(12.dp));Text(q?.change?.let(::pct)?:"—",color=q?.change?.let(::pnl)?:MUTED)}}
@Composable fun SectorRow(s:Sector,onClick:()->Unit){Card(Modifier.fillMaxWidth().clickable{onClick()},shape=RoundedCornerShape(16.dp)){Row(Modifier.padding(14.dp),verticalAlignment=Alignment.CenterVertically){Column(Modifier.weight(1f)){Text(s.name,fontWeight=FontWeight.Bold);Text("${s.status} · Breadth ${s.breadth}%",fontSize=11.sp,color=MUTED)};Text("RS ${s.rs}",color=BLUE,fontWeight=FontWeight.Bold)}}}
@Composable fun StockRow(s:Stock,q:Quote?,onClick:()->Unit){Card(Modifier.fillMaxWidth().clickable{onClick()},shape=RoundedCornerShape(16.dp)){Row(Modifier.padding(14.dp),verticalAlignment=Alignment.CenterVertically){Column(Modifier.weight(1f)){Text(s.name,fontWeight=FontWeight.Bold);Text("${s.code} · ${s.line}",fontSize=11.sp,color=MUTED);Text(s.pools.sorted().joinToString(" "),fontSize=10.sp,color=BLUE)};Column(horizontalAlignment=Alignment.End){Text(q?.price?.let{DecimalFormat("0.00").format(it)}?:"—",fontWeight=FontWeight.Bold);Text(q?.change?.let(::pct)?:"—",color=q?.change?.let(::pnl)?:MUTED,fontSize=11.sp);Text("RS ${s.rs}",fontSize=10.sp,color=BLUE)}}}}
@Composable fun Chips(xs:List<String>,sel:String,on:(String)->Unit){LazyRow(horizontalArrangement=Arrangement.spacedBy(7.dp)){items(xs){x->FilterChip(selected=x==sel,onClick={on(x)},label={Text(x)})}}}
@Composable fun KV(k:String,v:String){Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Text(k,fontSize=12.sp,color=MUTED);Text(v,fontSize=12.sp,fontWeight=FontWeight.SemiBold)}}

object Market{
 suspend fun fetchQuotes(symbols:List<String>):Map<String,Quote> = withContext(Dispatchers.IO){val c=(URL("https://qt.gtimg.cn/q="+symbols.distinct().joinToString(",")).openConnection() as HttpURLConnection).apply{connectTimeout=7000;readTimeout=7000;setRequestProperty("User-Agent","Mozilla/5.0 Android AStockStrategy")};try{val text=c.inputStream.use{it.readBytes()}.toString(Charset.forName("GBK"));val out=linkedMapOf<String,Quote>();Regex("v_([a-zA-Z0-9]+)=\\\"([^\\\"]*)\\\"").findAll(text).forEach{m->val f=m.groupValues[2].split("~");if(f.size>34)out[m.groupValues[1]]=Quote(m.groupValues[1],f.getOrNull(1).orEmpty(),f.getOrNull(2).orEmpty(),f.getOrNull(3)?.toDoubleOrNull(),f.getOrNull(4)?.toDoubleOrNull(),f.getOrNull(32)?.toDoubleOrNull(),f.getOrNull(33)?.toDoubleOrNull(),f.getOrNull(34)?.toDoubleOrNull(),f.getOrNull(37)?.toDoubleOrNull(),f.getOrNull(30))};out}finally{c.disconnect()}}
 suspend fun fetchBoard(name:String):Board?=withContext(Dispatchers.IO){val rows=boardList("m:90+t:2+f:!50")+boardList("m:90+t:3+f:!50");val r=rows.firstOrNull{it.name==name}?:rows.firstOrNull{it.name.contains(name)||name.contains(it.name)}?:return@withContext null;r.copy(members=members(r.code))}
 private fun boardList(fs:String):List<Board>{val u="https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=500&po=1&np=1&fltt=2&invt=2&fid=f3&fs="+URLEncoder.encode(fs,"UTF-8")+"&fields=f3,f6,f12,f14,f62,f184,f104,f105,f106";val a=json(u).optJSONObject("data")?.optJSONArray("diff")?:return emptyList();return buildList{for(i in 0 until a.length()){val x=a.optJSONObject(i)?:continue;add(Board(x.optString("f12"),x.optString("f14"),d(x,"f3"),d(x,"f6"),d(x,"f62"),d(x,"f184"),x.optInt("f104"),x.optInt("f105"),x.optInt("f106"),emptyList()))}}}
 private fun members(code:String):List<Member>{val u="https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=100&po=1&np=1&fltt=2&invt=2&fid=f3&fs="+URLEncoder.encode("b:$code","UTF-8")+"&fields=f2,f3,f6,f12,f14,f62";val a=json(u).optJSONObject("data")?.optJSONArray("diff")?:return emptyList();return buildList{for(i in 0 until a.length()){val x=a.optJSONObject(i)?:continue;add(Member(x.optString("f12"),x.optString("f14"),d(x,"f2"),d(x,"f3"),d(x,"f6"),d(x,"f62")))}}}
 suspend fun fetchFlow(code:String):FundFlow?=withContext(Dispatchers.IO){val sec=if(code.startsWith("6")||code.startsWith("5")||code.startsWith("9"))"1.$code" else "0.$code";val u="https://push2.eastmoney.com/api/qt/stock/fflow/kline/get?secid=$sec&klt=1&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57";val a=json(u).optJSONObject("data")?.optJSONArray("klines")?:return@withContext null;if(a.length()==0)return@withContext null;val p=a.optString(a.length()-1).split(",");FundFlow(p.getOrNull(0).orEmpty(),p.getOrNull(1)?.toDoubleOrNull(),p.getOrNull(4)?.toDoubleOrNull(),p.getOrNull(5)?.toDoubleOrNull(),p.getOrNull(3)?.toDoubleOrNull(),p.getOrNull(2)?.toDoubleOrNull())}
 private fun json(u:String):JSONObject{val c=(URL(u).openConnection() as HttpURLConnection).apply{connectTimeout=8000;readTimeout=10000;setRequestProperty("User-Agent","Mozilla/5.0 Android AStockStrategy");setRequestProperty("Referer","https://quote.eastmoney.com/")};return try{JSONObject(c.inputStream.bufferedReader().use{it.readText()})}finally{c.disconnect()}}
 private fun d(j:JSONObject,k:String):Double?{if(!j.has(k)||j.isNull(k))return null;val v=j.optDouble(k,Double.NaN);return if(v.isNaN())null else v}
}

private fun symbol(c:String)=if(c.startsWith("6")||c.startsWith("5")||c.startsWith("9"))"sh$c" else "sz$c"
private fun pct(v:Double)=(if(v>=0)"+" else "")+String.format("%.2f%%",v)
private fun pnl(v:Double)=if(v>=0)UP else DOWN
private fun money(v:Double)=when{v>=1e12->String.format("%.2f万亿",v/1e12);v>=1e8->String.format("%.1f亿",v/1e8);else->DecimalFormat("#,##0").format(v)}
private fun signedMoney(v:Double):String{val a=kotlin.math.abs(v);val b=if(a>=1e8)String.format("%.2f亿",a/1e8) else if(a>=1e4)String.format("%.1f万",a/1e4) else DecimalFormat("#,##0").format(a);return if(v<0)"-$b" else "+$b"}
private fun poolName(p:String)=when(p){"B0"->"B0 Base（基础池）";"B1"->"B1 Margin（两融增强）";"B2"->"B2 ETF（ETF增强）";"B3"->"B3 Main Flow（主力增强）";else->"B4 Combined（联合池）"}
