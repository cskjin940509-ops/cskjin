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
import java.time.LocalDate
import java.time.ZoneId
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
    var tailStock by mutableStateOf<TailStock?>(null)

    fun openSector(board: Board, date: String? = null) {
        sector = DetailSectorRef(board.name, board, date)
        stockCode = null
        stockDate = null
        tailStock = null
    }

    fun openSectorName(name: String, date: String?) {
        sector = DetailSectorRef(name, null, date)
        stockCode = null
        stockDate = null
        tailStock = null
    }

    fun openStock(code: String, date: String?) {
        stockCode = code
        stockDate = date
        tailStock = null
    }

    fun openTailStock(stock: TailStock, date: String?) {
        stockCode = stock.code
        stockDate = date
        tailStock = stock
    }

    fun back() {
        if (stockCode != null) {
            stockCode = null
            stockDate = null
            tailStock = null
        } else {
            sector = null
        }
    }

    fun reset() {
        sector = null
        stockCode = null
        stockDate = null
        tailStock = null
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
    val dayOpen: Double?,
    val dayClose: Double?,
    val dayHigh: Double?,
    val dayLow: Double?,
    val dayRangePct: Double?,
    val pools: List<String>,
    val priceProviders: List<String>,
    val priceMaxRelDiff: Double?
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
    suspend fun fetchSector(date: String, name: String): SectorFacts? = withContext(Dispatchers.IO) {
        val all = JSONArray(BackendClient.fetchText("astock_snapshots/index.json"))
        var day: JSONObject? = null
        for (i in 0 until all.length()) {
            val o = all.optJSONObject(i) ?: continue
            if (o.optString("date") == date) { day = o; break }
        }
        val dayObj = day ?: return@withContext null

        var selected: JSONObject? = null
        val selectedArr = dayObj.optJSONArray("selectedSectors")
        if (selectedArr != null) {
            for (i in 0 until selectedArr.length()) {
                val x = selectedArr.optJSONObject(i) ?: continue
                if (x.optString("name") == name) { selected = x; break }
            }
        }

        var heat: JSONObject? = null
        var kind: String? = selected?.optString("type")?.takeIf { it.isNotBlank() }
        val hm = dayObj.optJSONObject("boardHeatmap")
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
            up = if (h?.has("up") == true) h.optInt("up") else null,
            down = if (h?.has("down") == true) h.optInt("down") else null,
            flat = if (h?.has("flat") == true) h.optInt("flat") else null,
            breadthPct = jsonNum(h, "breadthPct") ?: jsonNum(base, "breadthPct"),
            rs20 = jsonNum(selected, "RS20"),
            rs60 = jsonNum(selected, "RS60"),
            mta = selected?.optString("MTA")?.takeIf { it.isNotBlank() },
            reason = selected?.optString("reason")?.takeIf { it.isNotBlank() },
            confidence = selected?.optString("confidence")?.takeIf { it.isNotBlank() }
        )
    }

    suspend fun fetchStock(date: String, code: String): StockFacts? = withContext(Dispatchers.IO) {
        val all = JSONArray(BackendClient.fetchText("astock_snapshots/index.json"))
        var day: JSONObject? = null
        for (i in 0 until all.length()) {
            val o = all.optJSONObject(i) ?: continue
            if (o.optString("date") == date) { day = o; break }
        }
        val dayObj = day ?: return@withContext null
        val x = dayObj.optJSONObject("stocks")?.optJSONObject(code) ?: return@withContext null
        val ps = mutableListOf<String>()
        val pa = x.optJSONArray("pools")
        if (pa != null) for (i in 0 until pa.length()) pa.optString(i).takeIf { it.isNotBlank() }?.let(ps::add)
        if (ps.isEmpty()) {
            val po = dayObj.optJSONObject("pools")
            listOf("B0", "B1", "B2", "B3", "B12", "B13", "B23", "B123", "B4").forEach { p ->
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
            dayOpen = jsonNum(x, "dayOpen"),
            dayClose = jsonNum(x, "dayClose") ?: jsonNum(x, "selectionPrice"),
            dayHigh = jsonNum(x, "dayHigh"),
            dayLow = jsonNum(x, "dayLow"),
            dayRangePct = jsonNum(x, "dayRangePct"),
            pools = ps.distinct().sorted(),
            priceProviders = run {
                val a = x.optJSONObject("priceValidation")?.optJSONArray("providers")
                if (a == null) emptyList() else (0 until a.length()).mapNotNull { i -> a.optString(i).takeIf { it.isNotBlank() } }
            },
            priceMaxRelDiff = jsonNum(x.optJSONObject("priceValidation"), "maxRelDiff")
        )
    }

    suspend fun fetchKline(secid: String, limit: Int = 90, endDate: String? = null): List<KBar> = withContext(Dispatchers.IO) {
        val end = endDate?.replace("-", "") ?: "20500101"
        val query = "secid=${enc(secid)}&klt=101&fqt=1&lmt=$limit&end=$end&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&ut=fa5fd1943c7b386f172d6893dbfba10b"
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

private fun stockSecid(code: String): String = (if (code.startsWith("5") || code.startsWith("6")) "1." else "0.") + code
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
            bars = runCatching { DetailApi.fetchKline(boardSecid(code), 90, historicalDate) }.getOrElse { emptyList() }
            members = runCatching { DetailApi.fetchMembers(code) }.getOrElse { emptyList() }
        }
        if (facts == null) error = "没有找到该板块的冻结数据或当前行情"
        loading = false
    }

    val f = facts
    val isFrozenMainline = historicalDate != null && snapshot?.date == historicalDate && snapshot.mainlines.contains(ref.name)
    val state = f?.status ?: if (isFrozenMainline) "正式主线" else "板块观察"
    val sectorPerf = snapshot?.sectorPerformance?.get(ref.name)
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
            item { DetailSectionTitle("策略后续跟踪") }
            item {
                DetailCard {
                    Text("从正式信号后的下一交易日可成交开盘起算，不把信号日涨幅计入策略收益。", color = DetailMuted, fontSize = 9.sp)
                    Spacer(Modifier.height(7.dp))
                    if (sectorPerf == null || sectorPerf.length() == 0) {
                        Text("当前尚未成熟 / 尚未同步", color = DetailMuted, fontSize = 10.sp)
                    } else {
                        TrackingStrip(sectorPerf)
                        Spacer(Modifier.height(6.dp))
                        DetailKey("当前跟踪收益", detailValue(sectorPerf, "current"))
                        DetailKey("最大浮盈", detailValue(sectorPerf, "MFE"))
                        DetailKey("最大回撤", detailValue(sectorPerf, "MAE"))
                        if (snapshot != null && !snapshot.performanceEligible) {
                            Text("参考收益跟踪 · 该批次不进入胜率、超额收益或因子成绩统计。", color = DetailMuted, fontSize = 9.sp)
                        }
                    }
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
    var bars by remember(code, snapshot?.date) { mutableStateOf<List<KBar>>(emptyList()) }
    var quote by remember(code) { mutableStateOf(initialQuote) }
    var loading by remember(code) { mutableStateOf(true) }
    var error by remember(code) { mutableStateOf<String?>(null) }
    val date = DetailNav.stockDate ?: snapshot?.date
    val tail = DetailNav.tailStock?.takeIf { it.code == code }
    val today = LocalDate.now(ZoneId.of("Asia/Shanghai")).toString()
    val historical = date != null && date < today

    LaunchedEffect(code, date) {
        loading = true
        error = null
        facts = date?.let { runCatching { DetailApi.fetchStock(it, code) }.getOrNull() }
        bars = runCatching { DetailApi.fetchKline(stockSecid(code), 90, date) }.getOrElse { emptyList() }
        if (!historical && quote == null) quote = runCatching { ResilientDataApi.fetchQuotes(listOf(symbol(code)))[symbol(code)] }.getOrNull()
        if (facts == null && quote == null && tail == null && bars.isEmpty()) error = "该股票的策略元数据和行情均暂不可用"
        loading = false
    }

    val meta = snapshot?.stocks?.get(code)
    val f = facts
    val name = f?.name ?: meta?.name ?: tail?.name ?: quote?.name ?: code
    val sector = f?.sector ?: meta?.sector ?: tail?.sector
    val pools = if (!f?.pools.isNullOrEmpty()) f!!.pools else snapshot?.pools?.filterValues { code in it }?.keys?.sorted().orEmpty()
    val selection = f?.selectionPrice ?: meta?.selectionPrice
    val displayPrice = if (historical) bars.lastOrNull()?.close ?: selection else quote?.price ?: bars.lastOrNull()?.close ?: selection
    val signalDayMove = f?.changePct ?: meta?.dayChangePct ?: tail?.changePct
    val perf = snapshot?.stockPerformance?.get(code)
    val providers = if (!f?.priceProviders.isNullOrEmpty()) f!!.priceProviders else meta?.priceProviders.orEmpty()
    val maxDiff = f?.priceMaxRelDiff ?: meta?.priceMaxRelDiff

    LazyColumn(modifier = Modifier.fillMaxSize().background(DetailBg), contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { DetailBackHeader("个股详情", "$name · $code", onBack) }
        item {
            StockTradingPanel26(
                code = code,
                name = name,
                fallbackPrice = null,
                sourceDate = date,
                poolLabels = pools,
                signal = null
            )
        }
        if (loading) item { DetailNotice("正在读取行情、策略因子、价格走势和收益跟踪数据…") }
        error?.let { item { DetailNotice(it) } }

        item {
            DetailCard {
                Row(verticalAlignment = Alignment.Top) {
                    Column(Modifier.weight(1f)) {
                        Text(name, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                        Text("$code · ${sector ?: "未关联板块"}", color = DetailMuted, fontSize = 11.sp)
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text(displayPrice?.let { String.format("%.2f", it) } ?: "数据未同步", fontSize = 22.sp, fontWeight = FontWeight.Bold)
                        Text(signalDayMove?.let { String.format("%+.2f%%", it) } ?: "当日涨跌未同步", color = if ((signalDayMove ?: 0.0) >= 0) DetailUp else DetailDown, fontSize = 11.sp)
                    }
                }
                if (pools.isNotEmpty()) {
                    Spacer(Modifier.height(8.dp))
                    Text("正式池：${pools.joinToString(" / ") { poolTitle(it) }}", color = DetailBlue, fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
                }
            }
        }

        if (tail != null) {
            item { DetailSectionTitle("尾盘决策上下文") }
            item {
                DetailCard {
                    DetailKey("尾盘捕获价", tail.price?.let { String.format("%.2f", it) } ?: "未同步")
                    DetailKey("尾盘评分", tail.tailScore?.let { String.format("%.1f", it) } ?: "未同步")
                    DetailKey("主力占比", tail.mainFlowPct?.let { String.format("%+.2f%%", it) } ?: "未同步")
                    DetailKey("风险", tail.risk)
                    DetailKey("云AI量化行情核对", if (tail.yunaiVerified == true) "通过" else "未确认")
                    DetailKey("云AI量化大单净流入", tail.yunaiLargeNetInflow?.let { String.format("%+.2f", it) } ?: "未同步")
                    tail.reason?.let { Text(it, fontSize = 9.sp, color = DetailMuted) }
                }
            }
        }

        item { DetailSectionTitle("信号日事实") }
        item {
            DetailCard {
                DetailKey("信号/入池日期", date ?: "未关联正式批次")
                DetailKey("未复权入池收盘价", selection?.let { String.format("%.2f", it) } ?: "未同步")
                DetailKey("信号日涨跌", signalDayMove?.let { String.format("%+.2f%%", it) } ?: "未同步")
                DetailKey("成交额", (f?.amount ?: meta?.amount ?: tail?.amount)?.let(::money) ?: "未同步")
                DetailKey("换手率", (f?.turnover ?: meta?.turnover ?: tail?.turnover)?.let { String.format("%.2f%%", it) } ?: "未同步")
                DetailKey("主力净流入", (f?.mainNetFlow ?: f?.mainNetFlow ?: tail?.mainNetFlow)?.let(::signedMoney) ?: "未同步")
                DetailKey("主力资金占比", (f?.mainFlowPct ?: f?.mainFlowPct ?: tail?.mainFlowPct)?.let { String.format("%+.2f%%", it) } ?: "未同步")
                if (providers.isNotEmpty()) DetailKey("入池价核验", providers.joinToString(" + "))
                if (maxDiff != null) DetailKey("开高低收最大源差", String.format("%.4f%%", maxDiff * 100.0))
            }
        }

        item { DetailSectionTitle("当日交易事实") }
        item {
            DetailCard {
                val hi = if (historical) f?.dayHigh ?: meta?.dayHigh else quote?.high ?: f?.dayHigh ?: meta?.dayHigh
                val lo = if (historical) f?.dayLow ?: meta?.dayLow else quote?.low ?: f?.dayLow ?: meta?.dayLow
                val op = f?.dayOpen ?: meta?.dayOpen
                val cl = if (historical) f?.dayClose ?: meta?.dayClose ?: selection else quote?.price ?: f?.dayClose ?: meta?.dayClose ?: selection
                val range = if (hi != null && lo != null && lo > 0) (hi / lo - 1.0) * 100.0 else f?.dayRangePct ?: meta?.dayRangePct
                DetailKey("当日开盘", op?.let { String.format("%.2f", it) } ?: "未同步")
                DetailKey("当日最高", hi?.let { String.format("%.2f", it) } ?: "未同步")
                DetailKey("当日最低", lo?.let { String.format("%.2f", it) } ?: "未同步")
                DetailKey("当前/收盘", cl?.let { String.format("%.2f", it) } ?: "未同步")
                DetailKey("理论高低区间", range?.let { String.format("%.2f%%", it) } ?: "未同步")
                Text("理论高低区间只描述最高与最低的价格跨度，不代表按时间顺序可实现的交易利润。", color = DetailMuted, fontSize = 9.sp)
            }
        }
        item { DetailSectionTitle("交易辅助") }
        item {
            if (snapshot != null) {
                val a = tradeAssist(code, snapshot, meta, if (historical) null else quote)
                DetailCard {
                    DetailKey("介入参考", a.entry)
                    DetailKey("持仓保护", a.holding)
                    Text(a.note, color = DetailMuted, fontSize = 9.sp)
                    Text("尚未录入你的实际成交价与持仓数量，因此离场提示目前只依据行情结构；加入“我的持仓”后再按真实成本计算止盈、止损和仓位。", color = DetailMuted, fontSize = 9.sp)
                }
            } else {
                DetailNotice("没有对应冻结批次，暂不生成交易辅助提示。")
            }
        }

        item { DetailSectionTitle("因子与模型") }
        item {
            DetailCard {
                DetailKey("综合评分", (f?.score ?: meta?.score)?.let { String.format("%.1f / 100", it) } ?: "未同步")
                DetailKey("20日相对强弱", (f?.rs20 ?: meta?.rs)?.let { String.format("%+.2f%%", it) } ?: "未同步")
                DetailKey("60日相对强弱", (f?.rs60 ?: meta?.rs60)?.let { String.format("%+.2f%%", it) } ?: "未同步")
                DetailKey("多周期趋势", f?.mta ?: meta?.mta ?: tail?.mta ?: "未同步")
                DetailKey("置信度", f?.confidence ?: meta?.confidence ?: "未标注")
                DetailKey("两融增强", if ("B1" in pools) "已确认" else "未入池/数据不足")
                DetailKey("指数基金一级申赎", if ("B2" in pools) "已确认" else "未入池/数据不足")
                DetailKey("主力资金确认", if ("B3" in pools) "已确认" else "未入池")
                (f?.reason ?: meta?.reason)?.let { Text(it, fontSize = 9.sp, color = DetailMuted) }
            }
        }

        item { DetailSectionTitle("价格走势（历史详情截止所选日期）") }
        item {
            DetailCard {
                if (bars.size < 5) Text("价格走势数据暂不可用", color = DetailMuted)
                else {
                    CandleChart(bars.takeLast(40))
                    Spacer(Modifier.height(8.dp))
                    DetailKey("5日涨跌", kReturn(bars, 5)?.let { String.format("%+.2f%%", it) } ?: "未成熟")
                    DetailKey("20日涨跌", kReturn(bars, 20)?.let { String.format("%+.2f%%", it) } ?: "未成熟")
                    DetailKey("60日涨跌", kReturn(bars, 60)?.let { String.format("%+.2f%%", it) } ?: "未成熟")
                    DetailKey("距20日高点", distHigh(bars, 20)?.let { String.format("%+.2f%%", it) } ?: "未成熟")
                }
            }
        }

        item { DetailSectionTitle("策略 后续收益跟踪") }
        item {
            DetailCard {
                if (perf == null || perf.length() == 0) {
                    Text(if (date == today) "该信号今天收盘形成；策略收益从下一交易日可成交开盘开始，因此今天不会把信号日前涨幅冒充策略收益。" else "后续收益跟踪 尚未同步或入场价尚未通过验证。", fontSize = 10.sp, color = DetailMuted)
                } else {
                    DetailKey("入场规则", perf.optString("entryRule", "次一交易日开盘"))
                    DetailKey("实际入场日", perf.optString("entryDate", "—"))
                    DetailKey("验证入场价", if (perf.has("entryPrice")) String.format("%.2f", perf.optDouble("entryPrice")) else "—")
                    TrackingStrip(perf)
                    Spacer(Modifier.height(8.dp))
                    DetailKey("当前跟踪", detailValue(perf, "current"))
                    DetailKey("最大浮盈", detailValue(perf, "MFE"))
                    DetailKey("最大回撤", detailValue(perf, "MAE"))
                    Text(if (snapshot?.performanceEligible == true) "该批次已通过审计，可纳入策略统计。" else "该批次为参考跟踪，不纳入胜率/Alpha或因子有效性统计。", fontSize = 9.sp, color = if (snapshot?.performanceEligible == true) DetailBlue else DetailMuted)
                }
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
