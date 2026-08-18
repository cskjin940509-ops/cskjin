package com.rui.astockstrategy.v5

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
import java.net.URLEncoder
import java.nio.charset.Charset
import java.text.DecimalFormat
import java.time.LocalDate
import java.time.YearMonth
import kotlin.math.abs

private val Bg = Color(0xFFF5F7FB)
private val Ink = Color(0xFF171A22)
private val Muted = Color(0xFF707788)
private val Blue = Color(0xFF3557D4)
private val Up = Color(0xFFD84343)
private val Down = Color(0xFF15966A)
private val Amber = Color(0xFFAE6A00)
private val SoftBlue = Color(0xFFE9EDFF)
private val SoftGreen = Color(0xFFE8F6F0)

data class Quote(val symbol:String,val name:String,val code:String,val price:Double?,val prev:Double?,val change:Double?,val high:Double?,val low:Double?,val amount:Double?,val time:String?)
data class Board(val code:String,val name:String,val change:Double?,val amount:Double?,val flow:Double?,val flowPct:Double?,val up:Int,val down:Int,val flat:Int,val type:String)
data class Member(val code:String,val name:String,val price:Double?,val change:Double?,val amount:Double?,val flow:Double?)
data class StockMeta(val code:String,val name:String?,val sector:String?,val rs:Double?,val mta:String?,val score:Double?,val reason:String?,val selectionPrice:Double?,val confidence:String?)
data class SectorSignal(val name:String,val status:String?,val score:Double?,val rs:Double?,val mta:String?,val breadth:Double?,val reason:String?,val confidence:String?)
data class Snapshot(
    val date:String,
    val status:String,
    val regime:String,
    val strategyVersion:String?,
    val mainlines:List<String>,
    val sectors:List<SectorSignal>,
    val pools:Map<String,List<String>>,
    val stocks:Map<String,StockMeta>,
    val added:List<String>,
    val removed:List<String>,
    val upgraded:List<String>,
    val downgraded:List<String>,
    val poolPerformance:Map<String,JSONObject>,
    val sectorPerformance:Map<String,JSONObject>,
    val stockPerformance:Map<String,JSONObject>,
    val note:String?
)

class V5Activity: ComponentActivity(){
    override fun onCreate(savedInstanceState: Bundle?){super.onCreate(savedInstanceState);setContent{AStockV5()}}
}

enum class Tab(val label:String,val icon:ImageVector){TODAY("今日",Icons.Default.Home),MARKET("行情",Icons.Default.GridView),MAINLINE("主线",Icons.Default.Radar),POOLS("股票池",Icons.Default.ViewList),HISTORY("历史",Icons.Default.CalendarMonth)}

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun AStockV5(){
    var tab by remember{mutableStateOf(Tab.TODAY)}
    var snapshots by remember{mutableStateOf<List<Snapshot>>(emptyList())}
    var selectedDate by remember{mutableStateOf<String?>(null)}
    var quotes by remember{mutableStateOf<Map<String,Quote>>(emptyMap())}
    var industries by remember{mutableStateOf<List<Board>>(emptyList())}
    var concepts by remember{mutableStateOf<List<Board>>(emptyList())}
    var selectedBoard by remember{mutableStateOf<Board?>(null)}
    var selectedCode by remember{mutableStateOf<String?>(null)}
    var dataStatus by remember{mutableStateOf("同步中")}

    val latest = snapshots.maxByOrNull{it.date}
    val active = selectedDate?.let{d->snapshots.firstOrNull{it.date==d}} ?: latest
    val activeCodes = active?.pools?.values?.flatten()?.distinct().orEmpty()

    LaunchedEffect(Unit){
        while(true){
            runCatching{DataApi.fetchSnapshots()}.onSuccess{if(it.isNotEmpty()){snapshots=it;dataStatus="Snapshot Live"}}.onFailure{dataStatus="Snapshot Error"}
            runCatching{DataApi.fetchBoards("industry")}.onSuccess{industries=it}
            runCatching{DataApi.fetchBoards("concept")}.onSuccess{concepts=it}
            delay(30000)
        }
    }
    LaunchedEffect(activeCodes.joinToString(",")){
        while(true){
            val symbols=(listOf("sh000001","sz399006","sh000688","sh000300","sh000852")+activeCodes.map(::symbol)).distinct()
            if(symbols.isNotEmpty()) runCatching{DataApi.fetchQuotes(symbols)}.onSuccess{if(it.isNotEmpty())quotes=it}
            delay(5000)
        }
    }

    MaterialTheme(colorScheme=lightColorScheme(primary=Blue,background=Bg,surface=Color.White,onSurface=Ink)){
        Scaffold(containerColor=Bg,
            topBar={TopAppBar(title={Column{Text("A股主线研究",fontWeight=FontWeight.Bold);Text(active?.let{"${it.date} · ${it.status} · ${it.regime}"}?:"等待每日策略快照",fontSize=11.sp,color=if(active?.status=="Official")Down else Amber)}},actions={Text(dataStatus,fontSize=10.sp,color=Muted,modifier=Modifier.padding(end=12.dp))})},
            bottomBar={NavigationBar{Tab.entries.forEach{t->NavigationBarItem(selected=tab==t,onClick={tab=t; if(t!=Tab.HISTORY) selectedDate=null},icon={Icon(t.icon,null)},label={Text(t.label)})}}}}
        ){pad->Box(Modifier.padding(pad).fillMaxSize()){
            when(tab){
                Tab.TODAY->TodayScreen(active,quotes,{selectedBoard=matchBoard(it,industries,concepts)},{selectedCode=it})
                Tab.MARKET->MarketScreen(industries,concepts){selectedBoard=it}
                Tab.MAINLINE->MainlineScreen(active,industries,concepts){selectedBoard=it}
                Tab.POOLS->PoolsScreen(active,quotes){selectedCode=it}
                Tab.HISTORY->HistoryScreen(snapshots,active,quotes,{selectedDate=it},{selectedBoard=matchBoard(it,industries,concepts)},{selectedCode=it})
            }
        }}
        selectedBoard?.let{b->BoardDialog(b,active,{selectedCode=it;selectedBoard=null}){selectedBoard=null}}
        selectedCode?.let{c->StockDialog(c,active,snapshots,quotes[symbol(c)]){selectedCode=null}}
    }
}

@Composable fun TodayScreen(s:Snapshot?,q:Map<String,Quote>,onSector:(String)->Unit,onStock:(String)->Unit){
    if(s==null){Empty("尚未读取到每日策略快照");return}
    LazyColumn(contentPadding=PaddingValues(14.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){
        item{Row(horizontalArrangement=Arrangement.spacedBy(10.dp)){Metric("Regime",s.regime,"${s.date} ${s.status}",Modifier.weight(1f));Metric("今日筛选",s.sectors.size.takeIf{it>0}?.toString()?:s.mainlines.size.toString(),"板块 / 主线",Modifier.weight(1f));Metric("B4",s.pools["B4"].orEmpty().size.toString(),"当日入选",Modifier.weight(1f))}}
        item{Notice(if(s.status=="Official")"这是当日冻结结果：后续只更新跟踪表现，不改写原名单。" else "Preview 仅表示当日尚未正式冻结；Official 到达后会替换同日 Preview。")}
        item{Title("当日筛选板块")}
        if((s.sectors.map{it.name}.ifEmpty{s.mainlines}).isEmpty()) item{EmptyCard("当天没有达到主线阈值的板块")} else items(s.sectors.map{it.name}.ifEmpty{s.mainlines}){n->DynamicSectorRow(n,s){onSector(n)}}
        item{Title("B4 Combined · 当日真实入选")}
        val b4=s.pools["B4"].orEmpty(); if(b4.isEmpty()) item{EmptyCard("当天 B4 无达标股票")} else items(b4){c->DynamicStockRow(c,s,q[symbol(c)]){onStock(c)}}
        item{DiffCard(s)}
    }
}

@Composable fun MarketScreen(ind:List<Board>,con:List<Board>,onBoard:(Board)->Unit){
    var type by remember{mutableStateOf("行业")};var sort by remember{mutableStateOf("涨跌")}
    val src=if(type=="行业")ind else con
    val sorted=when(sort){"资金"->src.sortedByDescending{it.flow?:Double.NEGATIVE_INFINITY};"广度"->src.sortedByDescending{breadth(it)};else->src.sortedByDescending{it.change?:Double.NEGATIVE_INFINITY}}
    LazyColumn(contentPadding=PaddingValues(14.dp),verticalArrangement=Arrangement.spacedBy(9.dp)){
        item{Choice(listOf("行业","概念"),type){type=it}}
        item{Choice(listOf("涨跌","资金","广度"),sort){sort=it}}
        item{Text("实时${type}热力图 · 公开行情事实",fontWeight=FontWeight.Bold,fontSize=17.sp)}
        items(sorted.take(80).chunked(2)){pair->Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){pair.forEach{b->HeatTile(b,Modifier.weight(1f)){onBoard(b)}};if(pair.size==1)Spacer(Modifier.weight(1f))}}
    }
}

@Composable fun MainlineScreen(s:Snapshot?,ind:List<Board>,con:List<Board>,onBoard:(Board)->Unit){
    if(s==null){Empty("暂无策略快照");return}
    val names=s.sectors.map{it.name}.ifEmpty{s.mainlines}
    LazyColumn(contentPadding=PaddingValues(14.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){
        item{Notice("这里不是固定板块榜：只展示 ${s.date} 当天按策略筛出来的板块；右侧 Live 数据只是当前行情，不会回写当日筛选。")}
        item{Title("Mainline Radar（主线雷达）")}
        if(names.isEmpty())item{EmptyCard("该日没有筛出主线板块")} else items(names){name->
            val sig=s.sectors.firstOrNull{it.name==name};val b=matchBoard(name,ind,con)
            Card(Modifier.fillMaxWidth().clickable{if(b!=null)onBoard(b)},shape=RoundedCornerShape(16.dp)){Column(Modifier.padding(14.dp)){Row{Column(Modifier.weight(1f)){Text(name,fontWeight=FontWeight.Bold);Text(sig?.status?:"Selected",fontSize=11.sp,color=Blue)};Text(b?.change?.let(::pct)?:"Live —",color=b?.change?.let(::pnl)?:Muted,fontWeight=FontWeight.Bold)};Spacer(Modifier.height(9.dp));RadarBars(sig,b)}}
        }
    }
}

@Composable fun PoolsScreen(s:Snapshot?,q:Map<String,Quote>,onStock:(String)->Unit){
    if(s==null){Empty("暂无策略快照");return};var pool by remember(s.date){mutableStateOf("B4")};val codes=s.pools[pool].orEmpty()
    LazyColumn(contentPadding=PaddingValues(14.dp),verticalArrangement=Arrangement.spacedBy(9.dp)){
        item{Choice(listOf("B0","B1","B2","B3","B4"),pool){pool=it}}
        item{Notice("${s.date} $pool 共 ${codes.size} 只。名单来自当天冻结 Daily Cohort，不从固定自选股生成。")}
        if(codes.isEmpty())item{EmptyCard("当天该股票池没有达标股票")} else items(codes){c->DynamicStockRow(c,s,q[symbol(c)]){onStock(c)}}
        item{PerformanceCard("$pool 后续表现",s.poolPerformance[pool])}
    }
}

@Composable fun HistoryScreen(all:List<Snapshot>,s:Snapshot?,q:Map<String,Quote>,onDate:(String)->Unit,onSector:(String)->Unit,onStock:(String)->Unit){
    if(all.isEmpty()){Empty("历史数据库为空");return};var pool by remember(s?.date){mutableStateOf("B4")};val latest=all.maxByOrNull{it.date}!!;val ym=YearMonth.parse((s?.date?:latest.date).substring(0,7))
    LazyColumn(contentPadding=PaddingValues(14.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){
        item{Title("Calendar Time Machine（日历时间机器）")};item{Calendar(ym,all,s?.date,onDate)}
        s?.let{snap->
            item{CardBlock{Row{Column(Modifier.weight(1f)){Text(snap.date,fontWeight=FontWeight.Bold,fontSize=18.sp);Text("${snap.status} · ${snap.regime}",fontSize=12.sp,color=if(snap.status=="Official")Down else Amber)};Text(snap.strategyVersion?:"Strategy",fontSize=11.sp,color=Muted)}}}
            item{Title("当天筛选板块 · 后续跟踪")}
            val names=snap.sectors.map{it.name}.ifEmpty{snap.mainlines};if(names.isEmpty())item{EmptyCard("当日无入选板块")} else items(names){n->HistorySectorRow(n,snap){onSector(n)}}
            item{Title("当天股票池")};item{Choice(listOf("B0","B1","B2","B3","B4"),pool){pool=it}}
            val codes=snap.pools[pool].orEmpty();if(codes.isEmpty())item{EmptyCard("当日该池为空")} else items(codes){c->HistoryStockRow(c,snap,q[symbol(c)]){onStock(c)}}
            item{PerformanceCard("$pool Cohort 后续表现",snap.poolPerformance[pool])}
            item{DiffCard(snap)}
            snap.note?.let{item{Notice(it)}}
        }
    }
}

@Composable fun Calendar(ym:YearMonth,all:List<Snapshot>,selected:String?,onDate:(String)->Unit){
    val byDate=all.associateBy{it.date};val first=ym.atDay(1);val offset=first.dayOfWeek.value%7;val total=offset+ym.lengthOfMonth();val cells=(0 until ((total+6)/7)*7).map{i->if(i<offset||i>=offset+ym.lengthOfMonth())null else ym.atDay(i-offset+1)}
    Card(shape=RoundedCornerShape(16.dp)){Column(Modifier.padding(10.dp)){Text("${ym.year}年${ym.monthValue}月",fontWeight=FontWeight.Bold);Spacer(Modifier.height(8.dp));Row{listOf("日","一","二","三","四","五","六").forEach{Text(it,Modifier.weight(1f),fontSize=10.sp,color=Muted)}};cells.chunked(7).forEach{week->Row{week.forEach{d->val snap=d?.let{byDate[it.toString()]};Box(Modifier.weight(1f).padding(2.dp).height(50.dp).background(if(d?.toString()==selected)SoftBlue else if(snap?.status=="Official")SoftGreen else Color.Transparent,RoundedCornerShape(9.dp)).clickable(enabled=snap!=null){onDate(d!!.toString())},contentAlignment=Alignment.Center){Column(horizontalAlignment=Alignment.CenterHorizontally){Text(d?.dayOfMonth?.toString()?:"",fontSize=12.sp,fontWeight=if(snap!=null)FontWeight.Bold else FontWeight.Normal);if(snap!=null)Text(if(snap.status=="Official")"●" else "◌",fontSize=9.sp,color=if(snap.status=="Official")Down else Amber)}}}}}}}
}

@Composable fun BoardDialog(board0:Board,s:Snapshot?,onStock:(String)->Unit,onClose:()->Unit){var members by remember(board0.code){mutableStateOf<List<Member>>(emptyList())};LaunchedEffect(board0.code){runCatching{DataApi.fetchMembers(board0.code)}.onSuccess{members=it}}
    AlertDialog(onDismissRequest=onClose,confirmButton={TextButton(onClick=onClose){Text("关闭")}},title={Column{Text(board0.name);Text("${board0.type} · ${board0.change?.let(::pct)?:"—"}",fontSize=12.sp,color=board0.change?.let(::pnl)?:Muted)}},text={LazyColumn(Modifier.heightIn(max=520.dp),verticalArrangement=Arrangement.spacedBy(8.dp)){item{Key("成交额",board0.amount?.let(::money)?:"—")};item{Key("上涨 / 下跌","${board0.up} / ${board0.down}")};item{Key("Breadth",String.format("%.0f%%",breadth(board0)))};item{Key("主力净流",board0.flow?.let(::signedMoney)?:"—")};item{Text("当日策略",fontWeight=FontWeight.Bold)};item{val sig=s?.sectors?.firstOrNull{it.name==board0.name};Text(if(sig!=null||s?.mainlines?.contains(board0.name)==true)"${s.date} 入选 · ${sig?.status?:"Selected"}" else "${s?.date?:"当前"} 未入选",color=if(sig!=null||s?.mainlines?.contains(board0.name)==true)Blue else Muted)};item{Text("成分股",fontWeight=FontWeight.Bold)};if(members.isEmpty())item{Text("加载中或公开接口暂无数据",color=Muted)} else items(members.take(50)){m->Row(Modifier.fillMaxWidth().clickable{onStock(m.code)}.padding(vertical=7.dp)){Column(Modifier.weight(1f)){Text(m.name,fontWeight=FontWeight.SemiBold);Text(m.code,fontSize=10.sp,color=Muted)};Column(horizontalAlignment=Alignment.End){Text(m.price?.let{DecimalFormat("0.00").format(it)}?:"—");Text(m.change?.let(::pct)?:"—",color=m.change?.let(::pnl)?:Muted,fontSize=11.sp)}}}}})
}

@Composable fun StockDialog(code:String,s:Snapshot?,all:List<Snapshot>,initial:Quote?,onClose:()->Unit){var q by remember(code){mutableStateOf(initial)};LaunchedEffect(code){if(q==null)runCatching{DataApi.fetchQuotes(listOf(symbol(code)))}.onSuccess{q=it[symbol(code)]}}
    val meta=s?.stocks?.get(code);val occurrences=all.sortedByDescending{it.date}.filter{snap->snap.pools.values.any{code in it}};val perf=s?.stockPerformance?.get(code)
    AlertDialog(onDismissRequest=onClose,confirmButton={TextButton(onClick=onClose){Text("关闭")}},title={Column{Text(meta?.name?:q?.name?:code);Text(code,fontSize=11.sp,color=Muted)}},text={LazyColumn(Modifier.heightIn(max=530.dp),verticalArrangement=Arrangement.spacedBy(8.dp)){item{Row{Text(q?.price?.let{DecimalFormat("0.00").format(it)}?:"—",fontWeight=FontWeight.Bold,fontSize=22.sp);Spacer(Modifier.width(10.dp));Text(q?.change?.let(::pct)?:"",color=q?.change?.let(::pnl)?:Muted)}};item{Key("当日所属板块",meta?.sector?:"—")};item{Key("当日 RS",meta?.rs?.let{String.format("%.1f",it)}?:"—")};item{Key("当日 MTA",meta?.mta?:"—")};item{Key("Selection Price",meta?.selectionPrice?.let{DecimalFormat("0.00").format(it)}?:"—")};item{Key("当日出现池",s?.pools?.filterValues{code in it}?.keys?.sorted()?.joinToString(" / ")?:"—")};item{Text("当日入选原因",fontWeight=FontWeight.Bold)};item{Text(meta?.reason?:"旧快照未保存个股原因字段",fontSize=12.sp,color=Muted)};item{PerformanceCard("该日入选后的 Forward Tracking",perf)};item{Text("历史入池记录",fontWeight=FontWeight.Bold)};if(occurrences.isEmpty())item{Text("暂无",color=Muted)} else items(occurrences.take(30)){x->Row(Modifier.fillMaxWidth()){Text(x.date,Modifier.weight(1f));Text(x.pools.filterValues{code in it}.keys.sorted().joinToString(" "),color=Blue,fontSize=11.sp)}}}})
}

@Composable fun DynamicSectorRow(name:String,s:Snapshot,onClick:()->Unit){val sig=s.sectors.firstOrNull{it.name==name};Card(Modifier.fillMaxWidth().clickable(onClick=onClick),shape=RoundedCornerShape(15.dp)){Row(Modifier.padding(13.dp)){Column(Modifier.weight(1f)){Text(name,fontWeight=FontWeight.Bold);Text(sig?.reason?:"${s.date} 当日筛选入选",fontSize=10.sp,color=Muted,maxLines=2)};Column(horizontalAlignment=Alignment.End){Text(sig?.status?:"Selected",color=Blue,fontSize=11.sp);Text(sig?.score?.let{"Score ${String.format("%.0f",it)}"}?:"",fontSize=10.sp,color=Muted)}}}}
@Composable fun DynamicStockRow(code:String,s:Snapshot,q:Quote?,onClick:()->Unit){val m=s.stocks[code];Card(Modifier.fillMaxWidth().clickable(onClick=onClick),shape=RoundedCornerShape(15.dp)){Row(Modifier.padding(13.dp)){Column(Modifier.weight(1f)){Text(m?.name?:q?.name?:code,fontWeight=FontWeight.Bold);Text("$code${m?.sector?.let{" · $it"}?:""}",fontSize=10.sp,color=Muted);Text(s.pools.filterValues{code in it}.keys.sorted().joinToString(" "),fontSize=10.sp,color=Blue)};Column(horizontalAlignment=Alignment.End){Text(q?.price?.let{DecimalFormat("0.00").format(it)}?:m?.selectionPrice?.let{DecimalFormat("0.00").format(it)}?:"—",fontWeight=FontWeight.Bold);Text(q?.change?.let(::pct)?:"",color=q?.change?.let(::pnl)?:Muted,fontSize=11.sp)}}}}
@Composable fun HistorySectorRow(name:String,s:Snapshot,onClick:()->Unit){val p=s.sectorPerformance[name];Card(Modifier.fillMaxWidth().clickable(onClick=onClick),shape=RoundedCornerShape(15.dp)){Column(Modifier.padding(12.dp)){Row{Text(name,Modifier.weight(1f),fontWeight=FontWeight.Bold);Text("${s.date} 入选",color=Blue,fontSize=11.sp)};TrackingStrip(p)}}}
@Composable fun HistoryStockRow(code:String,s:Snapshot,q:Quote?,onClick:()->Unit){val m=s.stocks[code];val p=s.stockPerformance[code];Card(Modifier.fillMaxWidth().clickable(onClick=onClick),shape=RoundedCornerShape(15.dp)){Column(Modifier.padding(12.dp)){Row{Column(Modifier.weight(1f)){Text(m?.name?:q?.name?:code,fontWeight=FontWeight.Bold);Text(code,fontSize=10.sp,color=Muted)};Text(s.pools.filterValues{code in it}.keys.sorted().joinToString(" "),color=Blue,fontSize=10.sp)};TrackingStrip(p)}}}

@Composable fun RadarBars(sig:SectorSignal?,b:Board?){val rows=listOf("Score" to sig?.score,"RS" to sig?.rs,"Breadth" to (sig?.breadth?:b?.let(::breadth)),"Live涨幅" to b?.change?.let{((it+10)*5).coerceIn(0.0,100.0)},"Flow" to b?.flowPct?.let{(50+it*2).coerceIn(0.0,100.0)});rows.forEach{(n,v)->Row(verticalAlignment=Alignment.CenterVertically,modifier=Modifier.padding(vertical=2.dp)){Text(n,Modifier.width(68.dp),fontSize=10.sp,color=Muted);LinearProgressIndicator(progress={((v?:0.0)/100.0).toFloat()},modifier=Modifier.weight(1f).height(6.dp));Spacer(Modifier.width(7.dp));Text(v?.let{String.format("%.0f",it)}?:"—",fontSize=10.sp)}};sig?.mta?.let{Text("MTA $it",fontSize=10.sp,color=Blue,modifier=Modifier.padding(top=4.dp))}}
@Composable fun HeatTile(b:Board,m:Modifier,onClick:()->Unit){val bg=when{(b.change?:0.0)>2->Color(0xFFFFE8E8);(b.change?:0.0)>0->Color(0xFFFFF3F0);(b.change?:0.0)<-2->Color(0xFFE4F4ED);(b.change?:0.0)<0->Color(0xFFEEF8F4);else->Color.White};Card(m.clickable(onClick=onClick),colors=CardDefaults.cardColors(containerColor=bg),shape=RoundedCornerShape(14.dp)){Column(Modifier.padding(11.dp)){Text(b.name,fontWeight=FontWeight.Bold,fontSize=13.sp,maxLines=1);Text(b.change?.let(::pct)?:"—",color=b.change?.let(::pnl)?:Muted,fontWeight=FontWeight.Bold);Text("广度 ${String.format("%.0f%%",breadth(b))}",fontSize=9.sp,color=Muted);Text(b.flow?.let{"资金 ${signedMoney(it)}"}?:"资金 —",fontSize=9.sp,color=Muted,maxLines=1)}}}

@Composable fun PerformanceCard(title:String,p:JSONObject?){CardBlock{Text(title,fontWeight=FontWeight.Bold);if(p==null||p.length()==0)Text("尚未成熟 / 尚未同步",color=Muted,fontSize=12.sp) else {TrackingStrip(p);val keys=p.keys().asSequence().toList().filterNot{it.matches(Regex("[0-9]+D",RegexOption.IGNORE_CASE))}.take(8);keys.forEach{k->val v=p.opt(k);if(v !is JSONObject && v !is JSONArray)Key(k,v?.toString()?:"—")}}}}
@Composable fun TrackingStrip(p:JSONObject?){Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(5.dp)){listOf("1D","5D","10D","20D","60D").forEach{h->val value=extractHorizon(p,h);Column(Modifier.weight(1f).background(Color(0xFFF3F5F9),RoundedCornerShape(8.dp)).padding(5.dp),horizontalAlignment=Alignment.CenterHorizontally){Text(h,fontSize=8.sp,color=Muted);Text(value,fontSize=9.sp,fontWeight=FontWeight.SemiBold)}}}}
fun extractHorizon(p:JSONObject?,h:String):String{if(p==null)return"—";val direct=p.opt(h);if(direct!=null&&direct!=JSONObject.NULL)return pretty(direct);val lc=h.lowercase();val it=p.keys();while(it.hasNext()){val k=it.next();if(k.lowercase()==lc||k.lowercase().contains(lc)){val v=p.opt(k);return pretty(v)}};return"—"}
fun pretty(v:Any?):String=when(v){null,JSONObject.NULL->"—";is Number->if(abs(v.toDouble())<2)String.format("%.2f%%",v.toDouble()*100) else String.format("%.2f",v.toDouble());is JSONObject->{val r=v.opt("return");if(r!=null&&r!=JSONObject.NULL)pretty(r) else v.opt("alpha").let{if(it!=null&&it!=JSONObject.NULL)pretty(it) else "✓"}};else->v.toString().take(12)}

@Composable fun Metric(t:String,v:String,sub:String,m:Modifier=Modifier){Card(m,shape=RoundedCornerShape(15.dp)){Column(Modifier.padding(11.dp)){Text(t,fontSize=9.sp,color=Muted);Text(v,fontWeight=FontWeight.Bold,fontSize=16.sp);Text(sub,fontSize=8.sp,color=Muted)}}}
@Composable fun CardBlock(c:@Composable ColumnScope.()->Unit){Card(shape=RoundedCornerShape(16.dp)){Column(Modifier.fillMaxWidth().padding(13.dp),content=c)}}
@Composable fun Title(t:String){Text(t,fontSize=17.sp,fontWeight=FontWeight.Bold)}
@Composable fun Notice(t:String){Card(colors=CardDefaults.cardColors(containerColor=SoftBlue),shape=RoundedCornerShape(13.dp)){Text(t,Modifier.fillMaxWidth().padding(11.dp),fontSize=11.sp,color=Ink)}}
@Composable fun Empty(t:String){Box(Modifier.fillMaxSize(),contentAlignment=Alignment.Center){Text(t,color=Muted)}}
@Composable fun EmptyCard(t:String){CardBlock{Text(t,color=Muted,fontSize=12.sp)}}
@Composable fun Key(k:String,v:String){Row(Modifier.fillMaxWidth().padding(vertical=2.dp)){Text(k,Modifier.weight(1f),fontSize=11.sp,color=Muted);Text(v,fontSize=11.sp,fontWeight=FontWeight.SemiBold)}}
@Composable fun Choice(values:List<String>,selected:String,on:(String)->Unit){LazyRow(horizontalArrangement=Arrangement.spacedBy(6.dp)){items(values){v->FilterChip(selected=v==selected,onClick={on(v)},label={Text(v)})}}}
@Composable fun DiffCard(s:Snapshot){CardBlock{Text("相对上一交易日 Diff",fontWeight=FontWeight.Bold);Key("新增",if(s.added.isEmpty())"—" else s.added.joinToString(", "));Key("移除",if(s.removed.isEmpty())"—" else s.removed.joinToString(", "));if(s.upgraded.isNotEmpty())Key("升级",s.upgraded.joinToString(", "));if(s.downgraded.isNotEmpty())Key("降级",s.downgraded.joinToString(", "))}}

fun matchBoard(name:String,ind:List<Board>,con:List<Board>):Board?{val all=ind+con;return all.firstOrNull{it.name==name}?:all.firstOrNull{it.name.contains(name)||name.contains(it.name)}}
fun breadth(b:Board):Double{val n=b.up+b.down+b.flat;return if(n<=0)0.0 else b.up*100.0/n}
fun symbol(code:String)=if(code.startsWith("6")||code.startsWith("5")||code.startsWith("9"))"sh$code" else "sz$code"
fun pct(v:Double)=(if(v>=0)"+" else "")+String.format("%.2f%%",v)
fun pnl(v:Double)=if(v>=0)Up else Down
fun money(v:Double)=when{abs(v)>=1e12->String.format("%.2f万亿",v/1e12);abs(v)>=1e8->String.format("%.2f亿",v/1e8);abs(v)>=1e4->String.format("%.1f万",v/1e4);else->DecimalFormat("#,##0").format(v)}
fun signedMoney(v:Double)=(if(v<0)"-" else "+")+money(abs(v))

object DataApi{
    private const val SNAP="https://raw.githubusercontent.com/cskjin940509-ops/cskjin/main/astock_snapshots/index.json"
    suspend fun fetchSnapshots():List<Snapshot>=withContext(Dispatchers.IO){val a=JSONArray(getText(SNAP));(0 until a.length()).mapNotNull{i->parseSnapshot(a.optJSONObject(i))}.sortedBy{it.date}}
    private fun parseSnapshot(o:JSONObject?):Snapshot?{o?:return null;val date=o.optString("date");if(date.isBlank())return null;val poolsO=o.optJSONObject("pools")?:JSONObject();val pools=(listOf("B0","B1","B2","B3","B4")).associateWith{k->arrStrings(poolsO.optJSONArray(k))};val stocksO=o.optJSONObject("stocks");val stocks=mutableMapOf<String,StockMeta>();if(stocksO!=null){val ks=stocksO.keys();while(ks.hasNext()){val c=ks.next();val x=stocksO.optJSONObject(c)?:continue;stocks[c]=StockMeta(c,x.optString("name").takeIf{it.isNotBlank()},x.optString("sector").takeIf{it.isNotBlank()},num(x,"RS")?:num(x,"rs"),x.optString("MTA").takeIf{it.isNotBlank()}?:x.optString("mta").takeIf{it.isNotBlank()},num(x,"score"),x.optString("reason").takeIf{it.isNotBlank()},num(x,"selectionPrice"),x.optString("confidence").takeIf{it.isNotBlank()})}}
        val sec=mutableListOf<SectorSignal>();val sa=o.optJSONArray("selectedSectors");if(sa!=null)for(i in 0 until sa.length()){val x=sa.opt(i);if(x is JSONObject){val n=x.optString("name");if(n.isNotBlank())sec+=SectorSignal(n,x.optString("status").takeIf{it.isNotBlank()},num(x,"score"),num(x,"RS")?:num(x,"rs"),x.optString("MTA").takeIf{it.isNotBlank()}?:x.optString("mta").takeIf{it.isNotBlank()},num(x,"Breadth")?:num(x,"breadth"),x.optString("reason").takeIf{it.isNotBlank()},x.optString("confidence").takeIf{it.isNotBlank()})}else if(x is String)sec+=SectorSignal(x,null,null,null,null,null,null,null)}
        val main=arrStrings(o.optJSONArray("mainlines"));return Snapshot(date,o.optString("status","Unknown"),o.optString("regime","Unknown"),o.optString("strategyVersion").takeIf{it.isNotBlank()},main,sec,pools,stocks,arrStrings(o.optJSONArray("added")),arrStrings(o.optJSONArray("removed")),arrStrings(o.optJSONArray("upgraded")),arrStrings(o.optJSONArray("downgraded")),objMap(o.optJSONObject("poolPerformance")?:o.optJSONObject("performance")),objMap(o.optJSONObject("sectorPerformance")),objMap(o.optJSONObject("stockPerformance")),o.optString("note").takeIf{it.isNotBlank()})}
    suspend fun fetchQuotes(symbols:List<String>):Map<String,Quote>=withContext(Dispatchers.IO){val u="https://qt.gtimg.cn/q=${symbols.distinct().joinToString(",")}";val text=getBytes(u).toString(Charset.forName("GBK"));val out=linkedMapOf<String,Quote>();Regex("v_([a-zA-Z0-9]+)=\\\"([^\\\"]*)\\\"").findAll(text).forEach{m->val f=m.groupValues[2].split("~");if(f.size>37){val s=m.groupValues[1];out[s]=Quote(s,f.getOrNull(1).orEmpty(),f.getOrNull(2).orEmpty(),f.getOrNull(3)?.toDoubleOrNull(),f.getOrNull(4)?.toDoubleOrNull(),f.getOrNull(32)?.toDoubleOrNull(),f.getOrNull(33)?.toDoubleOrNull(),f.getOrNull(34)?.toDoubleOrNull(),f.getOrNull(37)?.toDoubleOrNull()?.times(10000),f.getOrNull(30))}};out}
    suspend fun fetchBoards(type:String):List<Board>=withContext(Dispatchers.IO){val fs=if(type=="industry")"m:90+t:2+f:!50" else "m:90+t:3+f:!50";boardList(fs,type)}
    suspend fun fetchMembers(boardCode:String):List<Member>=withContext(Dispatchers.IO){val fs=URLEncoder.encode("b:$boardCode","UTF-8");val u="https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=100&po=1&np=1&fltt=2&invt=2&fid=f3&fs=$fs&fields=f2,f3,f6,f12,f14,f62";val a=getJson(u).optJSONObject("data")?.optJSONArray("diff")?:return@withContext emptyList();(0 until a.length()).mapNotNull{i->val x=a.optJSONObject(i)?:return@mapNotNull null;Member(x.optString("f12"),x.optString("f14"),num(x,"f2"),num(x,"f3"),num(x,"f6"),num(x,"f62"))}}
    private fun boardList(fs0:String,type:String):List<Board>{val fs=URLEncoder.encode(fs0,"UTF-8");val u="https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=500&po=1&np=1&fltt=2&invt=2&fid=f3&fs=$fs&fields=f3,f6,f12,f14,f62,f184,f104,f105,f106";val a=getJson(u).optJSONObject("data")?.optJSONArray("diff")?:return emptyList();return (0 until a.length()).mapNotNull{i->val x=a.optJSONObject(i)?:return@mapNotNull null;Board(x.optString("f12"),x.optString("f14"),num(x,"f3"),num(x,"f6"),num(x,"f62"),num(x,"f184"),x.optInt("f104"),x.optInt("f105"),x.optInt("f106"),type)}}
    private fun arrStrings(a:JSONArray?):List<String>{if(a==null)return emptyList();return (0 until a.length()).mapNotNull{i->a.optString(i).takeIf{it.isNotBlank()}}}
    private fun objMap(o:JSONObject?):Map<String,JSONObject>{if(o==null)return emptyMap();val m=linkedMapOf<String,JSONObject>();val it=o.keys();while(it.hasNext()){val k=it.next();val v=o.optJSONObject(k);if(v!=null)m[k]=v};return m}
    private fun num(o:JSONObject,k:String):Double?{if(!o.has(k)||o.isNull(k))return null;val v=o.optDouble(k,Double.NaN);return if(v.isNaN())null else v}
    private fun getJson(u:String)=JSONObject(getText(u))
    private fun getText(u:String)=getBytes(u).toString(Charsets.UTF_8)
    private fun getBytes(u:String):ByteArray{val c=(URL(u).openConnection() as HttpURLConnection).apply{connectTimeout=8000;readTimeout=10000;setRequestProperty("User-Agent","Mozilla/5.0 Android AStockStrategy");setRequestProperty("Referer","https://quote.eastmoney.com/")};return try{c.inputStream.use{it.readBytes()}}finally{c.disconnect()}}
}
