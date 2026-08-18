package com.rui.astockstrategy

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items as gridItems
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
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
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.sin

private val VBg = Color(0xFFF5F6FA)
private val VCard = Color.White
private val VInk = Color(0xFF151923)
private val VMuted = Color(0xFF727887)
private val VBlue = Color(0xFF3157D5)
private val VRed = Color(0xFFD94949)
private val VGreen = Color(0xFF168B67)
private val VAmber = Color(0xFFB56A00)
private val VGrid = Color(0xFFE7E9EF)

data class V4Quote(val code:String,val name:String,val price:Double?,val change:Double?,val high:Double?,val low:Double?,val amount:Double?,val time:String?)
data class HBoard(val code:String,val name:String,val change:Double?,val amount:Double?,val flow:Double?,val flowPct:Double?,val up:Int,val down:Int,val flat:Int)
data class HMember(val code:String,val name:String,val price:Double?,val change:Double?,val amount:Double?,val flow:Double?)
data class V4Flow(val time:String,val main:Double?,val superLarge:Double?,val large:Double?,val mid:Double?,val small:Double?)
data class LineModel(val name:String,val rs:Int,val breadth:Int,val status:String,val mta:Int)
data class Snapshot(
    val date:String,val status:String,val regime:String,val mainlines:List<String>,val pools:Map<String,List<String>>,
    val performance:JSONObject?,val added:List<String>,val removed:List<String>,val note:String
)

private val lineModels = listOf(
    LineModel("半导体设备",94,81,"Confirmed",92),
    LineModel("CPO/光通信",92,76,"Confirmed",90),
    LineModel("AI PCB",87,72,"Confirmed",84),
    LineModel("先进封装",83,68,"Candidate",73),
    LineModel("机器人",74,61,"Candidate",66),
    LineModel("创新药",66,55,"Rotation",54)
)

private val stockNames = mapOf(
    "002371" to "北方华创","688012" to "中微公司","300308" to "中际旭创","300502" to "新易盛",
    "688008" to "澜起科技","688072" to "拓荆科技","002384" to "东山精密","688361" to "中科飞测",
    "300604" to "长川科技","688981" to "中芯国际","688120" to "华海清科","300394" to "天孚通信",
    "300476" to "胜宏科技","002916" to "深南电路","688200" to "华峰测控","600183" to "生益科技",
    "688017" to "绿的谐波","002281" to "光迅科技"
)

class V04Activity: ComponentActivity(){
    override fun onCreate(savedInstanceState: Bundle?){super.onCreate(savedInstanceState);setContent{V04App()}}
}

enum class VTab(val label:String,val icon:ImageVector){
    HOME("首页",Icons.Default.Home), MARKET("行情",Icons.Default.GridView), MAINLINE("主线",Icons.Default.Radar),
    POOLS("股票池",Icons.Default.ViewList), HISTORY("历史",Icons.Default.CalendarMonth)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun V04App(){
    var tab by remember{mutableStateOf(VTab.HOME)}
    var selectedBoard by remember{mutableStateOf<HBoard?>(null)}
    var selectedStock by remember{mutableStateOf<String?>(null)}
    var snapshots by remember{mutableStateOf<List<Snapshot>>(emptyList())}
    var snapshotStatus by remember{mutableStateOf("同步中")}
    var refreshKey by remember{mutableIntStateOf(0)}

    LaunchedEffect(refreshKey){
        runCatching{V4Data.fetchSnapshots()}.onSuccess{snapshots=it;snapshotStatus=if(it.isNotEmpty())"已同步" else "本地"}.onFailure{snapshotStatus="离线"}
    }

    MaterialTheme(colorScheme=lightColorScheme(primary=VBlue,background=VBg,surface=VCard,onSurface=VInk)){
        when{
            selectedStock!=null -> StockPageV4(selectedStock!!, snapshots){selectedStock=null}
            selectedBoard!=null -> BoardPageV4(selectedBoard!!, onBack={selectedBoard=null}, onStock={selectedStock=it})
            else -> Scaffold(
                containerColor=VBg,
                topBar={TopAppBar(title={Column{Text("A股主线研究",fontWeight=FontWeight.Bold);Text("v0.4 · Live Preview + Official Snapshot",fontSize=10.sp,color=VMuted)}},actions={Text(snapshotStatus,fontSize=11.sp,color=if(snapshotStatus=="已同步")VGreen else VAmber);IconButton(onClick={refreshKey++}){Icon(Icons.Default.Refresh,null)}})},
                bottomBar={NavigationBar{VTab.entries.forEach{t->NavigationBarItem(selected=tab==t,onClick={tab=t},icon={Icon(t.icon,null)},label={Text(t.label)})}}}}
            ){p->Box(Modifier.padding(p).fillMaxSize()){
                when(tab){
                    VTab.HOME->HomeV4(snapshots,onBoard={selectedBoard=it},go={tab=it})
                    VTab.MARKET->MarketV4(onBoard={selectedBoard=it})
                    VTab.MAINLINE->MainlineV4(onBoard={selectedBoard=it})
                    VTab.POOLS->PoolsV4(snapshots,onStock={selectedStock=it})
                    VTab.HISTORY->HistoryV4(snapshots,onStock={selectedStock=it})
                }
            }}
        }
    }
}

@Composable
fun HomeV4(snapshots:List<Snapshot>,onBoard:(HBoard)->Unit,go:(VTab)->Unit){
    val latest=snapshots.maxByOrNull{it.date}
    var boards by remember{mutableStateOf<List<HBoard>>(emptyList())}
    LaunchedEffect(Unit){runCatching{V4Data.fetchBoards(false)}.onSuccess{boards=it}}
    LazyColumn(contentPadding=PaddingValues(14.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){
        item{Row(horizontalArrangement=Arrangement.spacedBy(10.dp)){MiniMetric("Regime",latest?.regime?:"震荡上行",latest?.status?:"Preview",Modifier.weight(1f));MiniMetric("B4",latest?.pools?.get("B4")?.size?.toString()?:"—","当前批次",Modifier.weight(1f))}}
        item{VSection{Row(verticalAlignment=Alignment.CenterVertically){Column(Modifier.weight(1f)){Text("实时行业热度",fontWeight=FontWeight.Bold);Text("公开行情事实 · 不等于正式主线确认",fontSize=10.sp,color=VMuted)};TextButton(onClick={go(VTab.MARKET)}){Text("全部")}};boards.sortedByDescending{it.change?:-999.0}.take(5).forEach{b->CompactBoardRow(b){onBoard(b)}}}}
        item{VSection{Text("主线雷达",fontWeight=FontWeight.Bold);Text("模型快照 + 实时板块事实分层展示",fontSize=10.sp,color=VMuted);Spacer(Modifier.height(8.dp));lineModels.take(3).forEach{m->Row(Modifier.fillMaxWidth().padding(vertical=5.dp)){Text(m.name,Modifier.weight(1f));Text(m.status,color=if(m.status=="Confirmed")VGreen else VAmber);Spacer(Modifier.width(10.dp));Text("RS ${m.rs}",color=VBlue,fontWeight=FontWeight.Bold)}};TextButton(onClick={go(VTab.MAINLINE)}){Text("打开主线雷达 →")}}}
        item{VSection{Text("历史与Forward Tracking",fontWeight=FontWeight.Bold);Text("每天Official批次永久冻结；1/5/10/20/60D成熟后自动回填。",fontSize=11.sp,color=VMuted);Spacer(Modifier.height(8.dp));Text("${snapshots.count{it.status=="Official"}} 个Official批次 · ${snapshots.size} 个历史快照",fontWeight=FontWeight.SemiBold);TextButton(onClick={go(VTab.HISTORY)}){Text("打开日历看板 →")}}}
    }
}

@Composable
fun MarketV4(onBoard:(HBoard)->Unit){
    var mode by remember{mutableStateOf("行业热力图")}
    var sort by remember{mutableStateOf("涨跌")}
    var boards by remember{mutableStateOf<List<HBoard>>(emptyList())}
    var loading by remember{mutableStateOf(true)}
    var refresh by remember{mutableIntStateOf(0)}
    LaunchedEffect(mode,refresh){
        if(mode!="指数"){loading=true;runCatching{V4Data.fetchBoards(mode=="概念热力图")}.onSuccess{boards=it}.also{loading=false}}
    }
    LaunchedEffect(mode){while(mode!="指数"){delay(30000);refresh++}}
    Column(Modifier.fillMaxSize()){
        LazyRow(Modifier.padding(horizontal=12.dp,vertical=8.dp),horizontalArrangement=Arrangement.spacedBy(7.dp)){items(listOf("指数","行业热力图","概念热力图")){x->FilterChip(selected=mode==x,onClick={mode=x},label={Text(x)})}}
        if(mode=="指数") IndexPanelV4()
        else{
            Row(Modifier.padding(horizontal=12.dp),verticalAlignment=Alignment.CenterVertically){Text("排序",fontSize=11.sp,color=VMuted);Spacer(Modifier.width(8.dp));listOf("涨跌","主力","广度").forEach{x->AssistChip(onClick={sort=x},label={Text(x)},colors=AssistChipDefaults.assistChipColors(containerColor=if(sort==x)Color(0xFFE8EDFF) else Color.Transparent));Spacer(Modifier.width(5.dp))};Spacer(Modifier.weight(1f));Text(if(loading)"刷新中" else "30s刷新",fontSize=10.sp,color=VMuted)}
            val shown=when(sort){"主力"->boards.sortedByDescending{it.flow?:Double.NEGATIVE_INFINITY};"广度"->boards.sortedByDescending{breadth(it)};else->boards.sortedByDescending{it.change?:Double.NEGATIVE_INFINITY}}
            if(loading&&boards.isEmpty()) Box(Modifier.fillMaxSize(),contentAlignment=Alignment.Center){CircularProgressIndicator()}
            else LazyVerticalGrid(columns=GridCells.Fixed(2),contentPadding=PaddingValues(10.dp),horizontalArrangement=Arrangement.spacedBy(8.dp),verticalArrangement=Arrangement.spacedBy(8.dp)){
                gridItems(shown.take(80)){b->HeatTile(b){onBoard(b)}}
            }
        }
    }
}

@Composable
fun IndexPanelV4(){
    var quotes by remember{mutableStateOf<Map<String,V4Quote>>(emptyMap())}
    LaunchedEffect(Unit){while(true){runCatching{V4Data.fetchQuotes(listOf("000001","399006","000688","000300","000852"))}.onSuccess{quotes=it};delay(5000)}}
    LazyColumn(contentPadding=PaddingValues(14.dp),verticalArrangement=Arrangement.spacedBy(8.dp)){
        item{VSection{Text("公开指数行情",fontWeight=FontWeight.Bold);Text("约5秒刷新",fontSize=10.sp,color=VMuted)}}
        items(listOf("000001" to "上证指数","399006" to "创业板指","000688" to "科创50","000300" to "沪深300","000852" to "中证1000")){(c,n)->val q=quotes[c];VSection{Row(verticalAlignment=Alignment.CenterVertically){Column(Modifier.weight(1f)){Text(n,fontWeight=FontWeight.Bold);Text(c,fontSize=10.sp,color=VMuted)};Column(horizontalAlignment=Alignment.End){Text(q?.price?.let{fmt2(it)}?:"—",fontWeight=FontWeight.Bold);Text(q?.change?.let{pct(it)}?:"—",color=q?.change?.let{pnl(it)}?:VMuted)}}}}
    }
}

@Composable
fun HeatTile(b:HBoard,onClick:()->Unit){
    val c=b.change?:0.0
    val bg=when{c>=3->Color(0xFFFFDADA);c>=1->Color(0xFFFFE9E9);c>0->Color(0xFFFFF4F4);c<=-3->Color(0xFFDDF5EC);c<=-1->Color(0xFFEAF8F3);else->Color(0xFFF4F5F8)}
    Card(Modifier.fillMaxWidth().height(106.dp).clickable(onClick=onClick),colors=CardDefaults.cardColors(containerColor=bg),shape=RoundedCornerShape(14.dp)){
        Column(Modifier.padding(12.dp)){Row{Text(b.name,Modifier.weight(1f),fontWeight=FontWeight.Bold,maxLines=1);Text(b.change?.let{pct(it)}?:"—",color=pnl(c),fontWeight=FontWeight.Bold)};Spacer(Modifier.height(9.dp));Text("Breadth ${(breadth(b)*100).toInt()}%",fontSize=10.sp,color=VMuted);Text("主力 ${b.flow?.let{signedMoney(it)}?:"—"}",fontSize=10.sp,color=if((b.flow?:0.0)>=0)VRed else VGreen);Text("成交 ${b.amount?.let{money(it)}?:"—"}",fontSize=10.sp,color=VMuted)}
    }
}

@Composable
fun MainlineV4(onBoard:(HBoard)->Unit){
    var selected by remember{mutableStateOf(lineModels.first())}
    var board by remember{mutableStateOf<HBoard?>(null)}
    LaunchedEffect(selected){runCatching{V4Data.findBoard(selected.name)}.onSuccess{board=it}}
    val liveBreadth=(board?.let{breadth(it)?.times(100)}?:selected.breadth.toDouble()).coerceIn(0.0,100.0)
    val momentum=(50.0+(board?.change?:0.0)*8.0).coerceIn(0.0,100.0)
    val flow=(50.0+(board?.flowPct?:0.0)*5.0).coerceIn(0.0,100.0)
    val values=listOf(selected.rs.toDouble(),liveBreadth,momentum,flow,selected.mta.toDouble())
    LazyColumn(contentPadding=PaddingValues(14.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){
        item{VSection{Text("Mainline Radar（主线雷达）",fontWeight=FontWeight.Bold);Text("RS / Breadth / Momentum / Flow / MTA",fontSize=11.sp,color=VMuted);Text("实时板块行情只更新Preview；Official主线仍按收盘可得数据冻结。",fontSize=10.sp,color=VAmber)}}
        item{LazyRow(horizontalArrangement=Arrangement.spacedBy(7.dp)){items(lineModels){m->FilterChip(selected=m==selected,onClick={selected=m},label={Text(m.name)})}}}
        item{VSection{Row{Column(Modifier.weight(1f)){Text(selected.name,fontWeight=FontWeight.Bold,fontSize=20.sp);Text(selected.status,color=if(selected.status=="Confirmed")VGreen else VAmber)};Column(horizontalAlignment=Alignment.End){Text(board?.change?.let{pct(it)}?:"—",fontWeight=FontWeight.Bold,color=board?.change?.let{pnl(it)}?:VMuted);Text("实时板块",fontSize=10.sp,color=VMuted)}};RadarChart(values,listOf("RS","Breadth","Momentum","Flow","MTA"),Modifier.fillMaxWidth().height(280.dp))}}
        item{VSection{Text("雷达拆解",fontWeight=FontWeight.Bold);listOf("RS" to values[0],"Breadth" to values[1],"Momentum" to values[2],"Flow" to values[3],"MTA" to values[4]).forEach{(k,v)->ScoreBar(k,v)};board?.let{TextButton(onClick={onBoard(it)}){Text("查看板块二级详情 →")}}}}
        item{VSection{Text("状态解释",fontWeight=FontWeight.Bold);Text("Confirmed：趋势+扩散+相对强度已经形成主线确认；Candidate：结构改善但确认不足；Rotation：更多视作轮动。",fontSize=11.sp,color=VMuted)}}
    }
}

@Composable
fun RadarChart(values:List<Double>,labels:List<String>,modifier:Modifier=Modifier){
    Canvas(modifier.padding(28.dp)){
        val cx=size.width/2;val cy=size.height/2;val r=minOf(size.width,size.height)*0.38f;val n=values.size
        fun point(i:Int,ratio:Float):Offset{val a=(-PI/2+2*PI*i/n).toFloat();return Offset(cx+cos(a)*r*ratio,cy+sin(a)*r*ratio)}
        for(level in 1..4){val path=Path();for(i in 0 until n){val p=point(i,level/4f);if(i==0)path.moveTo(p.x,p.y) else path.lineTo(p.x,p.y)};path.close();drawPath(path,VGrid,style=Stroke(1.dp.toPx()))}
        for(i in 0 until n){drawLine(VGrid,Offset(cx,cy),point(i,1f),1.dp.toPx())}
        val data=Path();for(i in 0 until n){val p=point(i,(values[i]/100.0).toFloat());if(i==0)data.moveTo(p.x,p.y) else data.lineTo(p.x,p.y)};data.close();drawPath(data,VBlue.copy(alpha=.18f));drawPath(data,VBlue,style=Stroke(2.dp.toPx()))
        labels.forEachIndexed{i,label->val p=point(i,1.22f);drawContext.canvas.nativeCanvas.drawText(label,p.x,p.y,android.graphics.Paint().apply{color=android.graphics.Color.DKGRAY;textSize=12.sp.toPx();textAlign=android.graphics.Paint.Align.CENTER})}
    }
}

@Composable
fun ScoreBar(label:String,value:Double){Column(Modifier.padding(vertical=5.dp)){Row{Text(label,Modifier.weight(1f),fontSize=11.sp,color=VMuted);Text(value.toInt().toString(),fontSize=11.sp,fontWeight=FontWeight.Bold)};LinearProgressIndicator(progress={value.toFloat()/100f},modifier=Modifier.fillMaxWidth().height(5.dp),color=VBlue,trackColor=VGrid)}}

@Composable
fun PoolsV4(snapshots:List<Snapshot>,onStock:(String)->Unit){
    val latest=snapshots.maxByOrNull{it.date}
    var pool by remember{mutableStateOf("B4")}
    var quotes by remember{mutableStateOf<Map<String,V4Quote>>(emptyMap())}
    val codes=latest?.pools?.get(pool).orEmpty()
    LaunchedEffect(codes){if(codes.isNotEmpty())runCatching{V4Data.fetchQuotes(codes)}.onSuccess{quotes=it}}
    LazyColumn(contentPadding=PaddingValues(14.dp),verticalArrangement=Arrangement.spacedBy(8.dp)){
        item{LazyRow(horizontalArrangement=Arrangement.spacedBy(7.dp)){items(listOf("B0","B1","B2","B3","B4")){p->FilterChip(selected=pool==p,onClick={pool=p},label={Text(p)})}}}
        item{VSection{Text("${latest?.date?:"—"} · ${latest?.status?:"未同步"}",fontWeight=FontWeight.Bold);Text(poolTitle(pool),fontSize=12.sp,color=VMuted);if(latest?.status=="Preview")Text("盘中Preview可变化；Official写入后永久冻结。",fontSize=10.sp,color=VAmber)}}
        if(codes.isEmpty()) item{VSection{Text("暂无批次数据",color=VMuted)}} else items(codes){c->val q=quotes[c];VSection(Modifier.clickable{onStock(c)}){Row(verticalAlignment=Alignment.CenterVertically){Column(Modifier.weight(1f)){Text(stockNames[c]?:c,fontWeight=FontWeight.Bold);Text(c,fontSize=10.sp,color=VMuted)};Column(horizontalAlignment=Alignment.End){Text(q?.price?.let{fmt2(it)}?:"—",fontWeight=FontWeight.Bold);Text(q?.change?.let{pct(it)}?:"实时",color=q?.change?.let{pnl(it)}?:VMuted,fontSize=11.sp)}}}}
    }
}

@Composable
fun HistoryV4(snapshots:List<Snapshot>,onStock:(String)->Unit){
    var selected by remember(snapshots){mutableStateOf(snapshots.maxByOrNull{it.date})}
    val ym=YearMonth.of(2026,8);val firstDow=LocalDate.of(2026,8,1).dayOfWeek.value-1
    LazyColumn(contentPadding=PaddingValues(12.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){
        item{VSection{Text("Calendar Time Machine（历史日历）",fontWeight=FontWeight.Bold);Text("点任意有记录的交易日，恢复当日主线、B0–B4和后续跟踪。",fontSize=11.sp,color=VMuted)}}
        item{Card(colors=CardDefaults.cardColors(containerColor=VCard),shape=RoundedCornerShape(16.dp)){Column(Modifier.padding(10.dp)){Text("2026年8月",fontWeight=FontWeight.Bold,modifier=Modifier.padding(6.dp));Row(Modifier.fillMaxWidth()){listOf("一","二","三","四","五","六","日").forEach{Text(it,Modifier.weight(1f),textAlign=TextAlign.Center,fontSize=10.sp,color=VMuted)}};Spacer(Modifier.height(4.dp));val total=firstDow+ym.lengthOfMonth();Column{for(row in 0 until (total+6)/7){Row(Modifier.fillMaxWidth()){for(col in 0..6){val idx=row*7+col;val day=idx-firstDow+1;if(day in 1..ym.lengthOfMonth()){val date="2026-08-${day.toString().padStart(2,'0')}";val s=snapshots.firstOrNull{it.date==date};DayCell(day,s,selected?.date==date,Modifier.weight(1f)){if(s!=null)selected=s}} else Spacer(Modifier.weight(1f).height(58.dp))}}}}}}}
        selected?.let{s->item{SnapshotDetail(s,onStock)}} ?: item{VSection{Text("暂无历史快照",color=VMuted)}}
    }
}

@Composable
fun RowScope.DayCell(day:Int,s:Snapshot?,selected:Boolean,modifier:Modifier=Modifier,onClick:()->Unit){
    val bg=when{selected->Color(0xFFE8EDFF);s?.status=="Official"->Color(0xFFEAF7F2);s!=null->Color(0xFFFFF3DF);else->Color.Transparent}
    Column(modifier.height(58.dp).padding(2.dp).background(bg,RoundedCornerShape(8.dp)).clickable(enabled=s!=null,onClick=onClick),horizontalAlignment=Alignment.CenterHorizontally){Text(day.toString(),fontSize=11.sp,modifier=Modifier.padding(top=5.dp));if(s!=null){Text(if(s.status=="Official")"O" else "P",fontSize=9.sp,color=if(s.status=="Official")VGreen else VAmber,fontWeight=FontWeight.Bold);Text("B4 ${s.pools["B4"]?.size?:0}",fontSize=8.sp,color=VMuted)}}
}

@Composable
fun SnapshotDetail(s:Snapshot,onStock:(String)->Unit){VSection{Text("${s.date} · ${s.status}",fontWeight=FontWeight.Bold,fontSize=18.sp);Text("Regime ${s.regime}",fontSize=11.sp,color=VMuted);Spacer(Modifier.height(8.dp));Text("当日主线",fontWeight=FontWeight.SemiBold);Text(s.mainlines.joinToString(" · "),fontSize=12.sp);Spacer(Modifier.height(10.dp));Text("B4 Combined",fontWeight=FontWeight.SemiBold);s.pools["B4"].orEmpty().forEach{c->Row(Modifier.fillMaxWidth().clickable{onStock(c)}.padding(vertical=5.dp)){Text(stockNames[c]?:c,Modifier.weight(1f));Text(c,fontSize=10.sp,color=VMuted)}};HorizontalDivider();Spacer(Modifier.height(8.dp));Text("Forward Tracking（前瞻跟踪）",fontWeight=FontWeight.SemiBold);PerformanceBlock(s.performance);if(s.added.isNotEmpty())Text("新增：${s.added.joinToString{stockNames[it]?:it}}",fontSize=10.sp,color=VGreen);if(s.removed.isNotEmpty())Text("移除：${s.removed.joinToString{stockNames[it]?:it}}",fontSize=10.sp,color=VRed);Text(s.note,fontSize=10.sp,color=VMuted,modifier=Modifier.padding(top=6.dp))}}

@Composable
fun PerformanceBlock(p:JSONObject?){
    if(p==null||p.length()==0){Text("尚无成熟周期；1/5/10/20/60D将在可交易窗口成熟后自动回填。",fontSize=11.sp,color=VMuted);return}
    val keys=p.keys().asSequence().toList().take(12)
    keys.forEach{k->val v=p.opt(k);when(v){is JSONObject->Text("$k  ${flattenJson(v)}",fontSize=10.sp,color=VMuted,modifier=Modifier.padding(vertical=2.dp));else->Text("$k  $v",fontSize=10.sp,color=VMuted)}}
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BoardPageV4(board0:HBoard,onBack:()->Unit,onStock:(String)->Unit){
    var board by remember{mutableStateOf(board0)};var members by remember{mutableStateOf<List<HMember>>(emptyList())};var page by remember{mutableStateOf("概览")}
    LaunchedEffect(board0.code){runCatching{V4Data.fetchMembers(board0.code)}.onSuccess{members=it};runCatching{V4Data.findBoard(board0.name)}.onSuccess{if(it!=null)board=it}}
    Scaffold(containerColor=VBg,topBar={TopAppBar(title={Column{Text(board.name,fontWeight=FontWeight.Bold);Text("板块二级详情",fontSize=10.sp,color=VMuted)}},navigationIcon={IconButton(onClick=onBack){Icon(Icons.Default.ArrowBack,null)}})}){p->LazyColumn(Modifier.padding(p),contentPadding=PaddingValues(14.dp),verticalArrangement=Arrangement.spacedBy(9.dp)){
        item{LazyRow(horizontalArrangement=Arrangement.spacedBy(7.dp)){items(listOf("概览","成分股","资金","策略")){x->FilterChip(selected=page==x,onClick={page=x},label={Text(x)})}}}
        when(page){
            "概览"->{item{VSection{BigQuote(board.change,board.amount);KeyRow("上涨 / 下跌 / 平","${board.up} / ${board.down} / ${board.flat}");KeyRow("Breadth","${(breadth(board)*100).toInt()}%");KeyRow("主力净流",board.flow?.let{signedMoney(it)}?:"—");KeyRow("主力净流占比",board.flowPct?.let{pct(it)}?:"—")}}}
            "成分股"->{if(members.isEmpty())item{VSection{Text("加载成分股…",color=VMuted)}} else items(members){m->VSection(Modifier.clickable{onStock(m.code)}){Row{Column(Modifier.weight(1f)){Text(m.name,fontWeight=FontWeight.Bold);Text(m.code,fontSize=10.sp,color=VMuted)};Column(horizontalAlignment=Alignment.End){Text(m.price?.let{fmt2(it)}?:"—");Text(m.change?.let{pct(it)}?:"—",color=m.change?.let{pnl(it)}?:VMuted)}}}}}
            "资金"->{item{VSection{KeyRow("主力净流",board.flow?.let{signedMoney(it)}?:"—");KeyRow("主力净流占比",board.flowPct?.let{pct(it)}?:"—");Text("公开成交单分类属于实验性资金数据，不代表真实机构账户。",fontSize=10.sp,color=VMuted)}}}
            else->{val model=lineModels.firstOrNull{it.name==board.name||it.name.contains(board.name)||board.name.contains(it.name)};item{VSection{KeyRow("模型状态",model?.status?:"Market only");KeyRow("RS",model?.rs?.toString()?:"未纳入");KeyRow("MTA",model?.mta?.toString()?:"—");Text("策略快照与实时板块涨跌分离；历史Official不会被盘中变化覆盖。",fontSize=10.sp,color=VMuted)}}}
        }
    }}
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StockPageV4(code:String,snapshots:List<Snapshot>,onBack:()->Unit){
    var q by remember{mutableStateOf<V4Quote?>(null)};var flow by remember{mutableStateOf<V4Flow?>(null)};var page by remember{mutableStateOf("行情")}
    LaunchedEffect(code){runCatching{V4Data.fetchQuotes(listOf(code))}.onSuccess{q=it[code]};runCatching{V4Data.fetchFlow(code)}.onSuccess{flow=it}}
    val history=snapshots.filter{s->s.pools.values.any{code in it}}.sortedByDescending{it.date}
    Scaffold(containerColor=VBg,topBar={TopAppBar(title={Column{Text(stockNames[code]?:q?.name?:code,fontWeight=FontWeight.Bold);Text("$code · 个股三级详情",fontSize=10.sp,color=VMuted)}},navigationIcon={IconButton(onClick=onBack){Icon(Icons.Default.ArrowBack,null)}})}){p->LazyColumn(Modifier.padding(p),contentPadding=PaddingValues(14.dp),verticalArrangement=Arrangement.spacedBy(9.dp)){
        item{LazyRow(horizontalArrangement=Arrangement.spacedBy(7.dp)){items(listOf("行情","趋势","资金","策略历史")){x->FilterChip(selected=page==x,onClick={page=x},label={Text(x)})}}}
        when(page){
            "行情"->{item{VSection{Row(verticalAlignment=Alignment.Bottom){Text(q?.price?.let{fmt2(it)}?:"—",fontSize=30.sp,fontWeight=FontWeight.Bold);Spacer(Modifier.width(10.dp));Text(q?.change?.let{pct(it)}?:"—",fontSize=16.sp,color=q?.change?.let{pnl(it)}?:VMuted)};KeyRow("日高 / 日低","${q?.high?.let{fmt2(it)}?:"—"} / ${q?.low?.let{fmt2(it)}?:"—"}");KeyRow("成交额",q?.amount?.let{money(it)}?:"—");KeyRow("行情时间",q?.time?:"—")}}}
            "趋势"->{item{VSection{Text("MTA / RS",fontWeight=FontWeight.Bold);Text("趋势页下一步接K线与MA20D / MA20W / MA10M；当前策略历史可从“策略历史”查看每次入池。",fontSize=11.sp,color=VMuted)}}}
            "资金"->{item{VSection{KeyRow("主力净流",flow?.main?.let{signedMoney(it)}?:"—");KeyRow("超大单",flow?.superLarge?.let{signedMoney(it)}?:"—");KeyRow("大单",flow?.large?.let{signedMoney(it)}?:"—");KeyRow("中单",flow?.mid?.let{signedMoney(it)}?:"—");Text("主力/大单为C级算法分类；正式两融信号遵守披露时点。",fontSize=10.sp,color=VMuted)}}}
            else->{if(history.isEmpty())item{VSection{Text("历史上尚未进入冻结池",color=VMuted)}} else items(history){s->val ps=s.pools.filterValues{code in it}.keys.sorted();VSection{Row{Text(s.date,Modifier.weight(1f),fontWeight=FontWeight.Bold);Text(s.status,color=if(s.status=="Official")VGreen else VAmber)};Text("进入 ${ps.joinToString(" / ")}",fontSize=11.sp,color=VBlue);PerformanceBlock(s.performance)}}}
        }
    }}
}

@Composable fun BigQuote(change:Double?,amount:Double?){Row(verticalAlignment=Alignment.Bottom){Text(change?.let{pct(it)}?:"—",fontSize=28.sp,fontWeight=FontWeight.Bold,color=change?.let{pnl(it)}?:VMuted);Spacer(Modifier.weight(1f));Text(amount?.let{money(it)}?:"—",fontSize=11.sp,color=VMuted)}}
@Composable fun KeyRow(k:String,v:String){Row(Modifier.fillMaxWidth().padding(vertical=5.dp)){Text(k,Modifier.weight(1f),fontSize=11.sp,color=VMuted);Text(v,fontSize=11.sp,fontWeight=FontWeight.SemiBold)}}
@Composable fun MiniMetric(t:String,v:String,sub:String,m:Modifier=Modifier){Card(m,shape=RoundedCornerShape(16.dp)){Column(Modifier.padding(14.dp)){Text(t,fontSize=10.sp,color=VMuted);Text(v,fontWeight=FontWeight.Bold,fontSize=18.sp);Text(sub,fontSize=9.sp,color=VMuted)}}}
@Composable fun VSection(modifier:Modifier=Modifier,content:@Composable ColumnScope.()->Unit){Card(modifier.fillMaxWidth(),shape=RoundedCornerShape(16.dp),colors=CardDefaults.cardColors(containerColor=VCard)){Column(Modifier.fillMaxWidth().padding(14.dp),content=content)}}
@Composable fun CompactBoardRow(b:HBoard,onClick:()->Unit){Row(Modifier.fillMaxWidth().clickable(onClick=onClick).padding(vertical=6.dp)){Text(b.name,Modifier.weight(1f));Text("${(breadth(b)*100).toInt()}%",fontSize=10.sp,color=VMuted);Spacer(Modifier.width(10.dp));Text(b.change?.let{pct(it)}?:"—",color=b.change?.let{pnl(it)}?:VMuted,fontWeight=FontWeight.Bold)}}

object V4Data{
    suspend fun fetchBoards(concept:Boolean):List<HBoard> = withContext(Dispatchers.IO){
        val fs=if(concept)"m:90+t:3+f:!50" else "m:90+t:2+f:!50";boardList(fs)
    }
    suspend fun findBoard(name:String):HBoard?=withContext(Dispatchers.IO){
        val all=boardList("m:90+t:2+f:!50")+boardList("m:90+t:3+f:!50")
        all.firstOrNull{it.name==name}?:all.firstOrNull{it.name.contains(name)||name.contains(it.name)||normalize(it.name)==normalize(name)}
    }
    suspend fun fetchMembers(boardCode:String):List<HMember> = withContext(Dispatchers.IO){
        val fs=URLEncoder.encode("b:$boardCode","UTF-8");val u="https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=100&po=1&np=1&fltt=2&invt=2&fid=f3&fs=$fs&fields=f2,f3,f6,f12,f14,f62";val a=json(u).optJSONObject("data")?.optJSONArray("diff")?:return@withContext emptyList();buildList{for(i in 0 until a.length()){val x=a.optJSONObject(i)?:continue;add(HMember(x.optString("f12"),x.optString("f14"),num(x,"f2"),num(x,"f3"),num(x,"f6"),num(x,"f62")))}}
    }
    suspend fun fetchQuotes(codes:List<String>):Map<String,V4Quote> = withContext(Dispatchers.IO){
        if(codes.isEmpty())return@withContext emptyMap();val syms=codes.distinct().map{marketSymbolV4(it)};val conn=(URL("https://qt.gtimg.cn/q=${syms.joinToString(",")}").openConnection() as HttpURLConnection).apply{connectTimeout=7000;readTimeout=7000;setRequestProperty("User-Agent","Mozilla/5.0 Android")};try{val text=conn.inputStream.use{it.readBytes()}.toString(Charset.forName("GBK"));val out=linkedMapOf<String,V4Quote>();Regex("v_([a-zA-Z0-9]+)=\\\"([^\\\"]*)\\\"").findAll(text).forEach{m->val f=m.groupValues[2].split("~");if(f.size>37){val code=f.getOrNull(2).orEmpty();out[code]=V4Quote(code,f.getOrNull(1).orEmpty(),f.getOrNull(3)?.toDoubleOrNull(),f.getOrNull(32)?.toDoubleOrNull(),f.getOrNull(33)?.toDoubleOrNull(),f.getOrNull(34)?.toDoubleOrNull(),f.getOrNull(37)?.toDoubleOrNull()?.times(10000),f.getOrNull(30))}};out}finally{conn.disconnect()}
    }
    suspend fun fetchFlow(code:String):V4Flow?=withContext(Dispatchers.IO){
        val market=if(code.startsWith("6")||code.startsWith("5")||code.startsWith("9"))"1" else "0";val u="https://push2.eastmoney.com/api/qt/stock/fflow/kline/get?secid=$market.$code&klt=1&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57";val a=json(u).optJSONObject("data")?.optJSONArray("klines")?:return@withContext null;if(a.length()==0)return@withContext null;val p=a.optString(a.length()-1).split(",");V4Flow(p.getOrNull(0).orEmpty(),p.getOrNull(1)?.toDoubleOrNull(),p.getOrNull(5)?.toDoubleOrNull(),p.getOrNull(4)?.toDoubleOrNull(),p.getOrNull(3)?.toDoubleOrNull(),p.getOrNull(2)?.toDoubleOrNull())
    }
    suspend fun fetchSnapshots():List<Snapshot> = withContext(Dispatchers.IO){
        val u="https://raw.githubusercontent.com/cskjin940509-ops/cskjin/main/astock_snapshots/index.json?t=${System.currentTimeMillis()}";val conn=(URL(u).openConnection() as HttpURLConnection).apply{connectTimeout=7000;readTimeout=10000;setRequestProperty("User-Agent","AStockStrategy/0.4")};try{val a=JSONArray(conn.inputStream.bufferedReader().use{it.readText()});buildList{for(i in 0 until a.length()){val x=a.optJSONObject(i)?:continue;val po=x.optJSONObject("pools");val pools=linkedMapOf<String,List<String>>();listOf("B0","B1","B2","B3","B4").forEach{k->pools[k]=arrStrings(po?.optJSONArray(k))};add(Snapshot(x.optString("date"),x.optString("status"),x.optString("regime"),arrStrings(x.optJSONArray("mainlines")),pools,x.optJSONObject("performance"),arrStrings(x.optJSONArray("added")),arrStrings(x.optJSONArray("removed")),x.optString("note")))}}}finally{conn.disconnect()}
    }
    private fun boardList(fsRaw:String):List<HBoard>{val fs=URLEncoder.encode(fsRaw,"UTF-8");val u="https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=500&po=1&np=1&fltt=2&invt=2&fid=f3&fs=$fs&fields=f3,f6,f12,f14,f62,f184,f104,f105,f106";val a=json(u).optJSONObject("data")?.optJSONArray("diff")?:return emptyList();return buildList{for(i in 0 until a.length()){val x=a.optJSONObject(i)?:continue;add(HBoard(x.optString("f12"),x.optString("f14"),num(x,"f3"),num(x,"f6"),num(x,"f62"),num(x,"f184"),x.optInt("f104"),x.optInt("f105"),x.optInt("f106")))}}}
    private fun json(u:String):JSONObject{val c=(URL(u).openConnection() as HttpURLConnection).apply{connectTimeout=8000;readTimeout=10000;setRequestProperty("User-Agent","Mozilla/5.0 Android AStockStrategy");setRequestProperty("Referer","https://quote.eastmoney.com/")};return try{JSONObject(c.inputStream.bufferedReader().use{it.readText()})}finally{c.disconnect()}}
    private fun num(x:JSONObject,k:String):Double?{if(!x.has(k)||x.isNull(k))return null;val v=x.optDouble(k,Double.NaN);return if(v.isNaN())null else v}
    private fun arrStrings(a:JSONArray?):List<String>{if(a==null)return emptyList();return buildList{for(i in 0 until a.length())add(a.optString(i))}}
    private fun normalize(s:String)=s.replace("概念","").replace("板块","").replace("设备","").replace("通信","").replace("/","")
}

private fun marketSymbolV4(code:String):String=when{code=="399006"->"sz399006";code.startsWith("399")->"sz$code";code=="000001"->"sh000001";code=="000688"->"sh000688";code=="000300"->"sh000300";code=="000852"->"sh000852";code.startsWith("6")||code.startsWith("5")||code.startsWith("9")->"sh$code";else->"sz$code"}
private fun breadth(b:HBoard):Double{val d=b.up+b.down+b.flat;return if(d<=0)0.0 else b.up.toDouble()/d}
private fun pct(v:Double)=String.format("%+.2f%%",v)
private fun fmt2(v:Double)=DecimalFormat("0.00").format(v)
private fun pnl(v:Double)=if(v>=0)VRed else VGreen
private fun money(v:Double)=when{abs(v)>=1e12->String.format("%.2f万亿",v/1e12);abs(v)>=1e8->String.format("%.2f亿",v/1e8);abs(v)>=1e4->String.format("%.1f万",v/1e4);else->DecimalFormat("#,##0").format(v)}
private fun signedMoney(v:Double)=(if(v>=0)"+" else "-")+money(abs(v))
private fun poolTitle(p:String)=when(p){"B0"->"Base（基础池）";"B1"->"Margin（两融增强）";"B2"->"ETF（ETF增强）";"B3"->"Main Flow（主力增强）";else->"Combined（联合池）"}
private fun flattenJson(o:JSONObject):String=o.keys().asSequence().take(4).joinToString("  "){k->"$k=${o.opt(k)}"}
