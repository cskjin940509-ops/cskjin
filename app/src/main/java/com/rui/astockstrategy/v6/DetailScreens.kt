package com.rui.astockstrategy.v6

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

private val DetailBg = Color(0xFFF5F7FB)
private val DetailMuted = Color(0xFF747B8D)
private val DetailBlue = Color(0xFF3557D4)
private val DetailUp = Color(0xFFD84343)
private val DetailDown = Color(0xFF15966A)
private val DetailSoftBlue = Color(0xFFE9EDFF)
private val DetailSoftGreen = Color(0xFFE8F6F0)

data class DetailSectorRef(val name: String, val board: Board? = null, val date: String? = null)

object DetailNav {
    var sector by mutableStateOf<DetailSectorRef?>(null)
    var stockCode by mutableStateOf<String?>(null)
    var stockDate by mutableStateOf<String?>(null)

    fun openSector(board: Board, date: String? = null) {
        sector = DetailSectorRef(board.name, board, date)
        stockCode = null
        stockDate = null
    }

    fun openSectorName(name: String, date: String?) {
        sector = DetailSectorRef(name, null, date)
        stockCode = null
        stockDate = null
    }

    fun openStock(code: String, date: String?) {
        stockCode = code
        stockDate = date
    }

    fun back() {
        if (stockCode != null) {
            stockCode = null
            stockDate = null
        } else {
            sector = null
        }
    }

    fun reset() {
        sector = null
        stockCode = null
        stockDate = null
    }
}

data class SectorFacts(
    val code: String,
    val name: String,
    val type: String?,
    val sourceDate: String?,
    val formalScore: Double?,
    val status: String?,
    val changePct: Double?,
    val amount: Double?,
    val mainNetFlow: Double?,
    val mainFlowPct: Double?,
    val up: Int?,
    val down: Int?,
    val flat: Int?,
    val breadthPct: Double?,
    val rs20: Double?,
    val rs60: Double?,
    val mta: String?,
    val reason: String?,
    val confidence: String?
)

data class StockFacts(
    val code: String,
    val name: String?,
    val sector: String?,
    val rs20: Double?,
    val rs60: Double?,
    val mta: String?,
    val score: Double?,
    val reason: String?,
    val selectionPrice: Double?,
    val confidence: String?,
    val changePct: Double?,
    val amount: Double?,
    val turnover: Double?,
    val mainNetFlow: Double?,
    val mainFlowPct: Double?,
    val pools: List<String>
)

data class KBar(
    val date: String,
    val open: Double?,
    val close: Double?,
    val high: Double?,
    val low: Double?,
    val amount: Double?
)

data class BoardMember(
    val code: String,
    val name: String,
    val price: Double?,
    val changePct: Double?,
    val amount: Double?,
    val mainNetFlow: Double?,
    val mainFlowPct: Double?
)

private fun jsonNum(o: JSONObject?, key: String): Double? {
    if (o == null) return null
    val v = o.opt(key)
    return when (v) {
        null, JSONObject.NULL -> null
        is Number -> v.toDouble()
        else -> v.toString().toDoubleOrNull()
    }
}

private object DetailApi {
    private const val SNAP = "https://raw.githubusercontent.com/cskjin940509-ops/cskjin/main/astock_snapshots/index.json"

    suspend fun fetchSector(date: String, name: String): SectorFacts? = withContext(Dispatchers.IO) {
        val all = JSONArray(getText(SNAP))
        var day: JSONObject? = null
        for (i in 0 until all.length()) {
            val o = all.optJSONObject(i) ?: continue
            if (o.optString("date") == date) { day = o; break }
        }
        day ?: return@withContext null

        var selected: JSONObject? = null
        val selectedArr = day.optJSONArray("selectedSectors")
        if (selectedArr != null) {
            for (i in 0 until selectedArr.length()) {
                val x = selectedArr.optJSONObject(i) ?: continue
                if (x.optString("name") == name) { selected = x; break }
            }
        }

        var heat: JSONObject? = null
        var kind: String? = selected?.optString("type")?.takeIf { it.isNotBlank() }
        val hm = day.optJSONObject("boardHeatmap")
        for ((key, zh) in listOf("industry" to "行业", "concept" to "概念")) {
            val a = hm?.optJSONArray(key) ?: continue
            for (i in 0 until a.length()) {
                val x = a.optJSONObject(i) ?: continue
                if (x.optString("name") == name) {
                    heat = x
                    if (kind == null) kind = zh
                    break
                }
            }
            if (heat != null) break
        }
        if (selected == null && heat == null) return@withContext null
        val base = selected ?: heat!!
        val h = heat ?: selected
        SectorFacts(
            code = selected?.optString("boardCode")?.takeIf { it.isNotBlank() }
                ?: heat?.optString("boardCode").orEmpty(),
            name = name,
            type = kind,
            sourceDate = date,
            formalScore = jsonNum(selected, "score"),
            status = selected?.optString("status")?.takeIf { it.isNotBlank() },
            changePct = jsonNum(h, "changePct") ?: jsonNum(base, "changePct"),
            amount = jsonNum(h, "amount") ?: jsonNum(base, "amount"),
            mainNetFlow = jsonNum(h, "mainNetFlow") ?: jsonNum(base, "mainNetFlow"),
            mainFlowPct = jsonNum(h, "mainFlowPct") ?: jsonNum(base, "mainFlowPct"),
            up = h?.optInt("up")?.takeIf { h.has("up") },
            down = h?.optInt("down")?.takeIf { h.has("down") },
            flat = h?.optInt("flat")?.takeIf { h.has("flat") },
            breadthPct = jsonNum(h, "breadthPct") ?: jsonNum(base, "breadthPct"),
            rs20 = jsonNum(selected, "RS20"),
            rs60 = jsonNum(selected, "RS60"),
            mta = selected?.optString("MTA")?.takeIf { it.isNotBlank() },
            reason = selected?.optString("reason")?.takeIf { it.isNotBlank() },
            confidence = selected?.optString("confidence")?.takeIf { it.isNotBlank() }
        )
    }

    suspend fun fetchStock(date: String, code: String): StockFacts? = withContext(Dispatchers.IO) {
        val all = JSONArray(getText(SNAP))
        var day: JSONObject? = null
        for (i in 0 until all.length()) {
            val o = all.optJSONObject(i) ?: continue
            if (o.optString("date") == date) { day = o; break }
        }
        val x = day?.optJSONObject("stocks")?.optJSONObject(code) ?: return@withContext null
        val ps = mutableListOf<String>()
        val pa = x.optJSONArray("pools")
        if (pa != null) for (i in 0 until pa.length()) pa.optString(i).takeIf { it.isNotBlank() }?.let(ps::add)
        if (ps.isEmpty()) {
            val po = day.optJSONObject("pools")
            listOf("B0", "B1", "B2", "B3", "B4").forEach { p ->
                val a = po?.optJSONArray(p) ?: return@forEach
                for (i in 0 until a.length()) if (a.optString(i) == code) { ps.add(p); break }
            }
        }
        StockFacts(
            code = code,
            name = x.optString("name").takeIf { it.isNotBlank() },
            sector = x.optString("sector").takeIf { it.isNotBlank() },
            rs20 = jsonNum(x, "RS") ?: jsonNum(x, "rs"),
            rs60 = jsonNum(x, "RS60") ?: jsonNum(x, "rs60"),
            mta = x.optString("MTA").takeIf { it.isNotBlank() } ?: x.optString("mta").takeIf { it.isNotBlank() },
            score = jsonNum(x, "score"),
            reason = x.optString("reason").takeIf { it.isNotBlank() },
            selectionPrice = jsonNum(x, "selectionPrice"),
            confidence = x.optString("confidence").takeIf { it.isNotBlank() },
            changePct = jsonNum(x, "changePct"),
            amount = jsonNum(x, "amount"),
            turnover = jsonNum(x, "turnover"),
            mainNetFlow = jsonNum(x, "mainNetFlow"),
            mainFlowPct = jsonNum(x, "mainFlowPct"),
            pools = ps.distinct().sorted()
        )
    }

    suspend fun fetchKline(secid: String, limit: Int = 90): List<KBar> = withContext(Dispatchers.IO) {
        val query = "secid=${enc(secid)}&klt=101&fqt=1&lmt=$limit&end=20500101&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&ut=fa5fd1943c7b386f172d6893dbfba10b"
        val root = JSONObject(getText("https://push2his.eastmoney.com/api/qt/stock/kline/get?$query"))
        val a = root.optJSONObject("data")?.optJSONArray("klines") ?: return@withContext emptyList()
        (0 until a.length()).mapNotNull { i ->
            val f = a.optString(i).split(',')
            if (f.size < 7) null else KBar(f[0], f[1].toDoubleOrNull(), f[2].toDoubleOrNull(), f[3].toDoubleOrNull(), f[4].toDoubleOrNull(), f[6].toDoubleOrNull())
        }
    }

    suspend fun fetchMembers(boardCode: String): List<BoardMember> = withContext(Dispatchers.IO) {
        if (boardCode.isBlank()) return@withContext emptyList()
        val fs = enc("b:$boardCode")
        val suffix = "api/qt/clist/get?pn=1&pz=40&po=1&np=1&fltt=2&invt=2&fid=f6&fs=$fs&fields=f2,f3,f6,f12,f14,f62,f184&ut=bd1d9ddb04089700cf9c27f6f7426281"
        var arr: JSONArray? = null
        for (host in listOf("push2.eastmoney.com", "push2delay.eastmoney.com")) {
            val got = runCatching { JSONObject(getText("https://$host/$suffix")).optJSONObject("data")?.optJSONArray("diff") }.getOrNull()
            if (got != null && got.length() > 0) { arr = got; break }
        }
        val a = arr ?: return@withContext emptyList()
        (0 until a.length()).mapNotNull { i ->
            val x = a.optJSONObject(i) ?: return@mapNotNull null
            val code = x.optString("f12")
            val name = x.optString("f14")
            if (code.isBlank() || name.isBlank()) null else BoardMember(
                code, name, jsonNum(x, "f2"), jsonNum(x, "f3"), jsonNum(x, "f6"), jsonNum(x, "f62"), jsonNum(x, "f184")
            )
        }
    }

    private fun enc(v: String) = URLEncoder.encode(v, "UTF-8")

    private fun getText(url: String): String {
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = 8000
        c.readTimeout = 8000
        c.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 Chrome/140 Mobile Safari/537.36")
        c.setRequestProperty("Accept", "*/*")
        c.setRequestProperty("Cache-Control", "no-cache")
        if (url.contains("eastmoney.com")) c.setRequestProperty("Referer", "https://quote.eastmoney.com/")
        c.connect()
        try {
            if (c.responseCode !in 200..299) error("HTTP ${c.responseCode}")
            return c.inputStream.bufferedReader().use { it.readText() }
        } finally { c.disconnect() }
    }
}

private fun sectorFromBoard(b: Board): SectorFacts = SectorFacts(
    code = b.code, name = b.name, type = if (b.type == "industry") "行业" else "概念", sourceDate = null,
    formalScore = null, status = null, changePct = b.change, amount = b.amount, mainNetFlow = b.flow,
    mainFlowPct = b.flowPct, up = b.up, down = b.down, flat = b.flat, breadthPct = breadth(b),
    rs20 = null, rs60 = null, mta = null, reason = null, confidence = null
)

private fun stockSecid(code: String): String = (if (code.startsWith("5") || code.startsWith("6") || code.startsWith("9")) "1." else "0.") + code
private fun boardSecid(code: String): String = "90.$code"

private fun kReturn(bars: List<KBar>, n: Int): Double? {
    val c = bars.mapNotNull { it.close }
    if (c.size <= n || c[c.size - 1 - n] == 0.0) return null
    return (c.last() / c[c.size - 1 - n] - 1.0) * 100.0
}

private fun kMa(bars: List<KBar>, n: Int): Double? {
    val c = bars.mapNotNull { it.close }
    if (c.size < n) return null
    return c.takeLast(n).average()
}

private fun distHigh(bars: List<KBar>, n: Int): Double? {
    val recent = bars.takeLast(n)
    if (recent.isEmpty()) return null
    val high = recent.mapNotNull { it.high ?: it.close }.maxOrNull() ?: return null
    val close = recent.lastOrNull()?.close ?: return null
    if (high == 0.0) return null
    return (close / high - 1.0) * 100.0
}

@Composable
fun SectorDetailScreen(ref: DetailSectorRef, snapshot: Snapshot?, onBack: () -> Unit) {
    var facts by remember(ref) { mutableStateOf(ref.board?.let(::sectorFromBoard)) }
    var bars by remember(ref) { mutableStateOf<List<KBar>>(emptyList()) }
    var members by remember(ref) { mutableStateOf<List<BoardMember>>(emptyList()) }
    var loading by remember(ref) { mutableStateOf(true) }
    var error by remember(ref) { mutableStateOf<String?>(null) }
    val historicalDate = ref.date ?: if (!marketOpenNow()) snapshot?.date else null

    LaunchedEffect(ref.name, ref.board?.code, historicalDate) {
        loading = true
        error = null
        val hist = historicalDate?.let { runCatching { DetailApi.fetchSector(it, ref.name) }.getOrNull() }
        if (hist != null) facts = hist
        val code = hist?.code?.takeIf { it.isNotBlank() } ?: ref.board?.code.orEmpty()
        if (code.isNotBlank()) {
            bars = runCatching { DetailApi.fetchKline(boardSecid(code)) }.getOrElse { emptyList() }
            members = runCatching { DetailApi.fetchMembers(code) }.getOrElse { emptyList() }
        }
        if (facts == null) error = "没有找到该板块的冻结数据或当前行情"
        loading = false
    }

    val f = facts
    val isFrozenMainline = historicalDate != null && snapshot?.date == historicalDate && snapshot.mainlines.contains(ref.name)
    val state = f?.status ?: if (isFrozenMainline) "正式主线" else "板块观察"
    val r5 = kReturn(bars, 5); val r20 = kReturn(bars, 20); val r60 = kReturn(bars, 60)
    val close = bars.lastOrNull()?.close
    val ma20 = kMa(bars, 20); val ma60 = kMa(bars, 60)
    val trend = when {
        close != null && ma20 != null && ma60 != null && close > ma20 && close > ma60 -> "日线趋势向上"
        close != null && ma20 != null && close > ma20 -> "短中期偏强"
        close != null && ma20 != null && close < ma20 -> "短期转弱"
        else -> "趋势数据待同步"
    }

    LazyColumn(modifier = Modifier.fillMaxSize().background(DetailBg), contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { DetailBackHeader("板块详情", ref.name, onBack) }
        if (loading) item { DetailNotice("正在读取板块趋势、资金和成分股…") }
        error?.let { item { DetailNotice(it) } }
        if (f != null) {
            item {
                DetailCard {
                    Row(verticalAlignment = Alignment.Top) {
                        Column(Modifier.weight(1f)) {
                            Text(f.name, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                            Text(listOfNotNull(f.type, historicalDate?.let { "$it 冻结截面" }).joinToString(" · "), color = DetailMuted, fontSize = 11.sp)
                        }
                        DetailTag(state, state.contains("主线"))
                    }
                    Spacer(Modifier.height(10.dp))
                    DetailKey("综合评分", f.formalScore?.let { String.format("%.1f / 100", it) } ?: "—")
                    DetailKey("当日涨跌", f.changePct?.let { String.format("%+.2f%%", it) } ?: "—")
                    DetailKey("20日相对强弱", f.rs20?.let { String.format("%+.2f%%", it) } ?: "—")
                    DetailKey("60日相对强弱", f.rs60?.let { String.format("%+.2f%%", it) } ?: "—")
                    DetailKey("多周期趋势", f.mta ?: trend)
                    DetailKey("置信度", f.confidence ?: "—")
                }
            }
            f.reason?.let { item { DetailExplain("模型解释", it) } }
            item { DetailSectionTitle("趋势") }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    DetailMetric("5日", r5?.let { String.format("%+.1f%%", it) } ?: "—", Modifier.weight(1f))
                    DetailMetric("20日", r20?.let { String.format("%+.1f%%", it) } ?: "—", Modifier.weight(1f))
                    DetailMetric("60日", r60?.let { String.format("%+.1f%%", it) } ?: "—", Modifier.weight(1f))
                }
            }
            item {
                DetailCard {
                    DetailKey("趋势判断", trend)
                    DetailKey("距20日高点", distHigh(bars, 20)?.let { String.format("%+.1f%%", it) } ?: "—")
                    DetailKey("距60日高点", distHigh(bars, 60)?.let { String.format("%+.1f%%", it) } ?: "—")
                }
            }
            item { DetailSectionTitle("资金") }
            item {
                DetailCard {
                    DetailKey("主力净流入", f.mainNetFlow?.let(::signedMoney) ?: "—")
                    DetailKey("主力资金占比", f.mainFlowPct?.let { String.format("%+.2f%%", it) } ?: "—")
                    DetailKey("成交额", f.amount?.let(::money) ?: "—")
                    DetailKey("5日累计主力净流入", "—")
                    Text("没有可靠历史资金序列时保持空值，不用当日值外推。", color = DetailMuted, fontSize = 9.sp)
                }
            }
            item { DetailSectionTitle("内部结构") }
            item {
                DetailCard {
                    DetailKey("上涨扩散度", f.breadthPct?.let { String.format("%.1f%%", it) } ?: "—")
                    DetailKey("上涨 / 下跌 / 平盘", "${f.up ?: "—"} / ${f.down ?: "—"} / ${f.flat ?: "—"}")
                    val total = listOfNotNull(f.up, f.down, f.flat).sum()
                    DetailKey("样本数", if (total > 0) total.toString() else "—")
                    Text("扩散度越高，越接近板块普涨；只靠少数权重拉升时这里会明显偏低。", color = DetailMuted, fontSize = 9.sp)
                }
            }
            item { DetailSectionTitle("成分股") }
            if (members.isEmpty()) item { DetailNotice("当前成分股列表暂未读到") }
            else {
                if (historicalDate != null) item { DetailNotice("下方为当前公开源成分股，用于继续下钻；历史策略结论仍以 $historicalDate 冻结截面为准。") }
                items(members.take(30)) { m ->
                    Card(Modifier.fillMaxWidth().clickable { DetailNav.openStock(m.code, historicalDate ?: snapshot?.date) }, shape = RoundedCornerShape(14.dp)) {
                        Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(m.name, fontWeight = FontWeight.Bold)
                                Text(m.code, color = DetailMuted, fontSize = 10.sp)
                            }
                            Column(horizontalAlignment = Alignment.End) {
                                Text(m.changePct?.let { String.format("%+.2f%%", it) } ?: "—", color = if ((m.changePct ?: 0.0) >= 0) DetailUp else DetailDown, fontWeight = FontWeight.Bold)
                                Text(m.mainNetFlow?.let { "主力 ${signedMoney(it)}" } ?: "主力 —", color = DetailMuted, fontSize = 9.sp)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun StockDetailScreen(code: String, snapshot: Snapshot?, initialQuote: Quote?, onBack: () -> Unit) {
    var facts by remember(code, snapshot?.date) { mutableStateOf<StockFacts?>(null) }
    var bars by remember(code) { mutableStateOf<List<KBar>>(emptyList()) }
    var quote by remember(code) { mutableStateOf(initialQuote) }
    var loading by remember(code) { mutableStateOf(true) }
    var error by remember(code) { mutableStateOf<String?>(null) }
    val date = DetailNav.stockDate ?: snapshot?.date

    LaunchedEffect(code, date) {
        loading = true
        error = null
        facts = date?.let { runCatching { DetailApi.fetchStock(it, code) }.getOrNull() }
        bars = runCatching { DetailApi.fetchKline(stockSecid(code)) }.getOrElse { emptyList() }
        if (quote == null) quote = runCatching { DataApi.fetchQuotes(listOf(symbol(code)))[symbol(code)] }.getOrNull()
        if (facts == null && quote == null) error = "该股票不在所选批次且实时行情暂不可用"
        loading = false
    }

    val meta = snapshot?.stocks?.get(code)
    val f = facts
    val name = f?.name ?: meta?.name ?: quote?.name ?: code
    val sector = f?.sector ?: meta?.sector
    val pools = if (!f?.pools.isNullOrEmpty()) f!!.pools else snapshot?.pools?.filterValues { code in it }?.keys?.sorted().orEmpty()
    val selection = f?.selectionPrice ?: meta?.selectionPrice
    val current = quote?.price ?: bars.lastOrNull()?.close
    val since = if (selection != null && selection > 0 && current != null) (current / selection - 1.0) * 100.0 else null
    val perf = snapshot?.stockPerformance?.get(code)

    LazyColumn(modifier = Modifier.fillMaxSize().background(DetailBg), contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { DetailBackHeader("个股详情", "$name · $code", onBack) }
        if (loading) item { DetailNotice("正在读取个股行情、K线和策略因子…") }
        error?.let { item { DetailNotice(it) } }
        item {
            DetailCard {
                Row(verticalAlignment = Alignment.Top) {
                    Column(Modifier.weight(1f)) {
                        Text(name, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                        Text("$code · ${sector ?: "未关联主线"}", color = DetailMuted, fontSize = 11.sp)
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text(current?.let { String.format("%.2f", it) } ?: "—", fontSize = 22.sp, fontWeight = FontWeight.Bold)
                        Text(quote?.change?.let { String.format("%+.2f%%", it) } ?: f?.changePct?.let { String.format("%+.2f%%", it) } ?: "—", color = if ((quote?.change ?: f?.changePct ?: 0.0) >= 0) DetailUp else DetailDown, fontSize = 11.sp)
                    }
                }
                if (pools.isNotEmpty()) {
                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) { pools.forEach { DetailTag(it, it == "B4") } }
                }
                Spacer(Modifier.height(8.dp))
                DetailKey("综合评分", f?.score?.let { String.format("%.1f / 100", it) } ?: meta?.score?.let { String.format("%.1f / 100", it) } ?: "—")
                DetailKey("入池日期", date ?: "—")
                DetailKey("入池价", selection?.let { String.format("%.2f", it) } ?: "—")
                DetailKey("入池后至今", since?.let { String.format("%+.2f%%", it) } ?: "—")
                DetailKey("置信度", f?.confidence ?: meta?.confidence ?: "—")
            }
        }
        val reason = f?.reason ?: meta?.reason
        item { DetailExplain("为什么入选", reason ?: "该股票不是当前所选 Daily Cohort 的冻结入选股；仍可查看行情和趋势。") }

        item { DetailSectionTitle("因子") }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    DetailMetric("20日相对强弱", f?.rs20?.let { String.format("%+.1f%%", it) } ?: meta?.rs?.let { String.format("%+.1f%%", it) } ?: "—", Modifier.weight(1f))
                    DetailMetric("60日相对强弱", f?.rs60?.let { String.format("%+.1f%%", it) } ?: "—", Modifier.weight(1f))
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    DetailMetric("多周期趋势", f?.mta ?: meta?.mta ?: "—", Modifier.weight(1f))
                    DetailMetric("主力资金占比", f?.mainFlowPct?.let { String.format("%+.1f%%", it) } ?: "—", Modifier.weight(1f))
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    DetailMetric("换手率", f?.turnover?.let { String.format("%.1f%%", it) } ?: "—", Modifier.weight(1f))
                    DetailMetric("成交额", f?.amount?.let(::money) ?: "—", Modifier.weight(1f))
                }
            }
        }
        item { DetailCard { DetailKey("主力净流入", f?.mainNetFlow?.let(::signedMoney) ?: "—"); DetailKey("两融增强 B1", if ("B1" in pools) "已入池" else "—"); DetailKey("ETF增强 B2", if ("B2" in pools) "已入池" else "—"); Text("B1/B2没有正式数据时保持空值，不用其他口径代替。", color = DetailMuted, fontSize = 9.sp) } }

        item { DetailSectionTitle("K线") }
        item {
            DetailCard {
                if (bars.size < 5) Text("K线数据暂不可用", color = DetailMuted)
                else {
                    CandleChart(bars.takeLast(40))
                    Spacer(Modifier.height(8.dp))
                    DetailKey("20日涨跌", kReturn(bars, 20)?.let { String.format("%+.2f%%", it) } ?: "—")
                    DetailKey("60日涨跌", kReturn(bars, 60)?.let { String.format("%+.2f%%", it) } ?: "—")
                    DetailKey("距20日高点", distHigh(bars, 20)?.let { String.format("%+.2f%%", it) } ?: "—")
                }
            }
        }

        item { DetailSectionTitle("资金") }
        item {
            DetailCard {
                DetailKey("当日主力净流入", f?.mainNetFlow?.let(::signedMoney) ?: "—")
                DetailKey("主力资金占比", f?.mainFlowPct?.let { String.format("%+.2f%%", it) } ?: "—")
                DetailKey("成交额", f?.amount?.let(::money) ?: "—")
                DetailKey("融资余额变化", "—")
                DetailKey("ETF申赎关联", "—")
            }
        }

        item { DetailSectionTitle("入池后表现") }
        item {
            DetailCard {
                DetailKey("入池价", selection?.let { String.format("%.2f", it) } ?: "—")
                DetailKey("当前/最近价", current?.let { String.format("%.2f", it) } ?: "—")
                DetailKey("累计收益", since?.let { String.format("%+.2f%%", it) } ?: "—")
                Spacer(Modifier.height(8.dp))
                TrackingStrip(perf)
                Spacer(Modifier.height(8.dp))
                DetailKey("最大有利涨幅", detailValue(perf, "MFE"))
                DetailKey("最大不利跌幅", detailValue(perf, "MAE"))
                DetailKey("超额收益", detailValue(perf, "alpha"))
                DetailKey("趋势存续期", detailValue(perf, "trendSurvival"))
            }
        }
    }
}

@Composable
private fun CandleChart(bars: List<KBar>) {
    val valid = bars.filter { it.close != null && (it.high ?: it.close) != null && (it.low ?: it.close) != null }
    if (valid.isEmpty()) return
    val hi = valid.mapNotNull { it.high ?: it.close }.maxOrNull() ?: return
    val lo = valid.mapNotNull { it.low ?: it.close }.minOrNull() ?: return
    val span = max(hi - lo, hi * 0.005)
    Canvas(Modifier.fillMaxWidth().height(180.dp).background(Color(0xFFF8F9FC), RoundedCornerShape(10.dp))) {
        val step = size.width / valid.size.coerceAtLeast(1)
        fun y(v: Double): Float = ((hi - v) / span * (size.height - 12f) + 6f).toFloat()
        valid.forEachIndexed { i, b ->
            val o = b.open ?: b.close ?: return@forEachIndexed
            val c = b.close ?: return@forEachIndexed
            val h = b.high ?: max(o, c)
            val l = b.low ?: min(o, c)
            val x = step * (i + 0.5f)
            val color = if (c >= o) DetailUp else DetailDown
            drawLine(color, Offset(x, y(h)), Offset(x, y(l)), strokeWidth = 1.2f)
            val top = min(y(o), y(c)); val bottom = max(y(o), y(c))
            drawRect(color, topLeft = Offset(x - step * 0.26f, top), size = Size(step * 0.52f, max(1.5f, bottom - top)))
        }
    }
}

private fun detailValue(o: JSONObject?, key: String): String {
    if (o == null) return "—"
    val direct = o.opt(key)
    if (direct != null && direct != JSONObject.NULL) return pretty(direct)
    val it = o.keys()
    while (it.hasNext()) {
        val k = it.next()
        if (k.equals(key, true) || k.contains(key, true)) return pretty(o.opt(k))
    }
    return "—"
}

@Composable
private fun DetailBackHeader(title: String, subtitle: String, onBack: () -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        TextButton(onClick = onBack) { Text("← 返回") }
        Column(Modifier.weight(1f)) {
            Text(title, fontWeight = FontWeight.Bold, fontSize = 18.sp)
            Text(subtitle, color = DetailMuted, fontSize = 10.sp, maxLines = 1)
        }
    }
}

@Composable
private fun DetailSectionTitle(text: String) { Text(text, fontSize = 17.sp, fontWeight = FontWeight.Bold) }

@Composable
private fun DetailCard(content: @Composable ColumnScope.() -> Unit) {
    Card(Modifier.fillMaxWidth(), shape = RoundedCornerShape(16.dp)) { Column(Modifier.fillMaxWidth().padding(13.dp), content = content) }
}

@Composable
private fun DetailKey(name: String, value: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 3.dp)) {
        Text(name, Modifier.weight(1f), color = DetailMuted, fontSize = 10.sp)
        Text(value, fontWeight = FontWeight.SemiBold, fontSize = 10.sp)
    }
}

@Composable
private fun DetailMetric(title: String, value: String, modifier: Modifier) {
    Card(modifier, colors = CardDefaults.cardColors(containerColor = Color.White), shape = RoundedCornerShape(14.dp)) {
        Column(Modifier.padding(11.dp)) {
            Text(title, color = DetailMuted, fontSize = 9.sp)
            Text(value, fontWeight = FontWeight.Bold, fontSize = 14.sp, maxLines = 2)
        }
    }
}

@Composable
private fun DetailTag(text: String, strong: Boolean) {
    Surface(color = if (strong) DetailSoftGreen else DetailSoftBlue, shape = RoundedCornerShape(20.dp)) {
        Text(text, color = if (strong) DetailDown else DetailBlue, fontWeight = FontWeight.Bold, fontSize = 9.sp, modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp))
    }
}

@Composable
private fun DetailExplain(title: String, text: String) {
    Surface(color = DetailSoftBlue, shape = RoundedCornerShape(15.dp)) {
        Column(Modifier.fillMaxWidth().padding(12.dp)) {
            Text(title, fontWeight = FontWeight.Bold, fontSize = 12.sp)
            Spacer(Modifier.height(4.dp))
            Text(text, fontSize = 11.sp, lineHeight = 17.sp)
        }
    }
}

@Composable
private fun DetailNotice(text: String) {
    Surface(color = DetailSoftBlue, shape = RoundedCornerShape(14.dp)) { Text(text, Modifier.fillMaxWidth().padding(11.dp), fontSize = 10.sp) }
}
