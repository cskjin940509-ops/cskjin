package com.rui.astockstrategy.v6

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
import kotlin.math.abs

private val HistMuted = Color(0xFF747B8D)
private val HistBlue = Color(0xFF3557D4)
private val HistUp = Color(0xFFD84343)
private val HistDown = Color(0xFF15966A)
private val HistSoftBlue = Color(0xFFE9EDFF)
private val HistSoftRed = Color(0xFFFFECEC)

data class HistIndex(
    val key: String,
    val name: String,
    val close: Double?,
    val changePct: Double?,
    val amount: Double?
)

data class HistBoard(
    val code: String,
    val name: String,
    val changePct: Double?,
    val amount: Double?,
    val up: Int?,
    val down: Int?,
    val flat: Int?,
    val breadthPct: Double?,
    val mainNetFlow: Double?,
    val mainFlowPct: Double?,
    val rs5: Double?,
    val rs20: Double?,
    val rs60: Double?,
    val mta: String?,
    val confidence: String?
)

data class HistMarket(
    val date: String,
    val indices: List<HistIndex>,
    val totalAmount: Double?,
    val up: Int?,
    val down: Int?,
    val flat: Int?,
    val limitUp: Int?,
    val limitDown: Int?,
    val medianChange: Double?,
    val ma5Breadth: Double?,
    val ma20Breadth: Double?,
    val ma60Breadth: Double?,
    val industry: List<HistBoard>,
    val concept: List<HistBoard>,
    val source: String?,
    val availableAt: String?,
    val backfilled: Boolean
)

@Composable
fun HistoricalMarketReplay(date: String) {
    var data by remember(date) { mutableStateOf<HistMarket?>(null) }
    var loading by remember(date) { mutableStateOf(true) }
    var error by remember(date) { mutableStateOf<String?>(null) }
    var mode by remember(date) { mutableStateOf("市场概览") }

    LaunchedEffect(date) {
        loading = true
        error = null
        runCatching { HistApi.fetch(date) }
            .onSuccess { data = it }
            .onFailure { error = it.javaClass.simpleName }
        loading = false
    }

    Column(verticalArrangement = Arrangement.spacedBy(9.dp)) {
        Text("历史市场回放", fontSize = 17.sp, fontWeight = FontWeight.Bold)
        Text("恢复 $date 当天市场截面；历史行情与当日策略名单相互独立，不用今天数据覆盖过去。", fontSize = 10.sp, color = HistMuted)
        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
            listOf("市场概览", "行业热力", "概念热力").forEachIndexed { index, item ->
                SegmentedButton(
                    selected = mode == item,
                    onClick = { mode = item },
                    shape = SegmentedButtonDefaults.itemShape(index, 3),
                    label = { Text(item, fontSize = 9.sp) }
                )
            }
        }
        when {
            loading -> HistNotice("正在读取 $date 历史市场快照…")
            error != null -> HistNotice("历史数据源读取失败（$error）。不会拿当前行情冒充历史。")
            data == null -> HistNotice("$date 的市场快照和板块热力图尚未同步；后台补齐后会自动出现。")
            mode == "市场概览" -> HistOverview(data!!)
            mode == "行业热力" -> HistHeatmap(data!!.industry, "行业", data!!.date)
            else -> HistHeatmap(data!!.concept, "概念", data!!.date)
        }
    }
}

@Composable
private fun HistOverview(m: HistMarket) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (m.backfilled) HistNotice("历史回填数据 · ${m.source ?: "公开历史行情"}；只回填可验证市场字段，不改写当日主线/B0-B4。")
        if (m.indices.isNotEmpty()) {
            m.indices.chunked(2).forEach { pair ->
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    pair.forEach { x ->
                        Card(Modifier.weight(1f), shape = RoundedCornerShape(14.dp)) {
                            Column(Modifier.padding(10.dp)) {
                                Text(x.name, fontSize = 10.sp, color = HistMuted)
                                Text(x.close?.let { String.format("%.2f", it) } ?: "—", fontWeight = FontWeight.Bold)
                                Text(x.changePct?.let { String.format("%+.2f%%", it) } ?: "—", color = histPnl(x.changePct), fontSize = 11.sp)
                                Text(x.amount?.let { histMoney(it) } ?: "成交额 —", fontSize = 8.sp, color = HistMuted)
                            }
                        }
                    }
                    if (pair.size == 1) Spacer(Modifier.weight(1f))
                }
            }
        } else HistNotice("该日指数截面尚未回填。")

        Card(shape = RoundedCornerShape(15.dp)) {
            Column(Modifier.fillMaxWidth().padding(12.dp)) {
                HistKey("全市场成交额", m.totalAmount?.let(::histMoney) ?: "—")
                HistKey("上涨 / 下跌 / 平盘", listOf(m.up, m.down, m.flat).joinToString(" / ") { it?.toString() ?: "—" })
                HistKey("涨停 / 跌停", "${m.limitUp ?: "—"} / ${m.limitDown ?: "—"}")
                HistKey("全A中位数", m.medianChange?.let { String.format("%+.2f%%", it) } ?: "—")
                HistKey("MA5以上", m.ma5Breadth?.let { String.format("%.1f%%", it) } ?: "—")
                HistKey("MA20以上", m.ma20Breadth?.let { String.format("%.1f%%", it) } ?: "—")
                HistKey("MA60以上", m.ma60Breadth?.let { String.format("%.1f%%", it) } ?: "—")
                m.availableAt?.let { HistKey("数据可得时间", it) }
            }
        }
    }
}

@Composable
private fun HistHeatmap(items: List<HistBoard>, title: String, date: String) {
    var sort by remember { mutableStateOf("涨跌") }
    val sorted = when (sort) {
        "资金" -> items.sortedByDescending { it.mainNetFlow ?: Double.NEGATIVE_INFINITY }
        "广度" -> items.sortedByDescending { it.breadthPct ?: Double.NEGATIVE_INFINITY }
        "20日相对强弱" -> items.sortedByDescending { it.rs20 ?: Double.NEGATIVE_INFINITY }
        else -> items.sortedByDescending { it.changePct ?: Double.NEGATIVE_INFINITY }
    }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
            listOf("涨跌", "资金", "广度", "20日相对强弱").forEachIndexed { index, item ->
                SegmentedButton(
                    selected = sort == item,
                    onClick = { sort = item },
                    shape = SegmentedButtonDefaults.itemShape(index, 4),
                    label = { Text(item, fontSize = 9.sp) }
                )
            }
        }
        if (sorted.isEmpty()) {
            HistNotice("该日${title}热力图数据尚未同步，不会拿今天行情冒充历史。")
        } else {
            sorted.take(120).chunked(2).forEach { pair ->
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    pair.forEach { b -> HistHeatTile(b, date, Modifier.weight(1f)) }
                    if (pair.size == 1) Spacer(Modifier.weight(1f))
                }
            }
        }
    }
}

@Composable
private fun HistHeatTile(b: HistBoard, date: String, modifier: Modifier) {
    val ch = b.changePct ?: 0.0
    val bg = when {
        ch > 2 -> HistSoftRed
        ch > 0 -> Color(0xFFFFF5F2)
        ch < -2 -> Color(0xFFE4F4ED)
        ch < 0 -> Color(0xFFEEF8F4)
        else -> Color.White
    }
    Card(modifier.clickable { DetailNav.openSectorName(b.name, date) }, colors = CardDefaults.cardColors(containerColor = bg), shape = RoundedCornerShape(14.dp)) {
        Column(Modifier.padding(10.dp)) {
            Text(b.name, fontWeight = FontWeight.Bold, fontSize = 12.sp, maxLines = 1)
            Text(b.changePct?.let { String.format("%+.2f%%", it) } ?: "—", color = histPnl(b.changePct), fontWeight = FontWeight.Bold)
            Text("广度 ${b.breadthPct?.let { String.format("%.0f%%", it) } ?: "—"} · 20日相对强弱 ${b.rs20?.let { String.format("%.0f", it) } ?: "—"}", fontSize = 8.sp, color = HistMuted)
            Text(b.mainNetFlow?.let { "资金 ${histSignedMoney(it)} · 点开详情" } ?: "资金未同步 · 点开详情", fontSize = 8.sp, color = HistMuted, maxLines = 1)
            if (!b.mta.isNullOrBlank()) Text("多周期趋势 ${b.mta}", fontSize = 8.sp, color = HistBlue)
        }
    }
}

@Composable
private fun HistNotice(text: String) {
    Surface(color = HistSoftBlue, shape = RoundedCornerShape(12.dp)) {
        Text(text, Modifier.fillMaxWidth().padding(10.dp), fontSize = 10.sp)
    }
}

@Composable
private fun HistKey(k: String, v: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
        Text(k, Modifier.weight(1f), fontSize = 9.sp, color = HistMuted)
        Text(v, fontSize = 9.sp, fontWeight = FontWeight.SemiBold)
    }
}

private fun histPnl(v: Double?): Color = if ((v ?: 0.0) >= 0) HistUp else HistDown
private fun histMoney(v: Double): String = when {
    abs(v) >= 1e12 -> String.format("%.2f万亿", v / 1e12)
    abs(v) >= 1e8 -> String.format("%.2f亿", v / 1e8)
    abs(v) >= 1e4 -> String.format("%.1f万", v / 1e4)
    else -> String.format("%.0f", v)
}
private fun histSignedMoney(v: Double): String = (if (v >= 0) "+" else "") + histMoney(v)

object HistApi {
    private const val SNAP = "https://raw.githubusercontent.com/cskjin940509-ops/cskjin/main/astock_snapshots/index.json"

    suspend fun fetch(date: String): HistMarket? = withContext(Dispatchers.IO) {
        val arr = JSONArray(getText(SNAP))
        var root: JSONObject? = null
        for (i in 0 until arr.length()) {
            val x = arr.optJSONObject(i) ?: continue
            if (x.optString("date") == date) { root = x; break }
        }
        val r = root ?: return@withContext null
        val market = r.optJSONObject("marketSnapshot")
        val heat = r.optJSONObject("boardHeatmap")
        if (market == null && heat == null) return@withContext null
        parse(date, market, heat)
    }

    private fun parse(date: String, m: JSONObject?, h: JSONObject?): HistMarket {
        val indices = mutableListOf<HistIndex>()
        val io = m?.opt("indices")
        when (io) {
            is JSONObject -> {
                val it = io.keys()
                while (it.hasNext()) {
                    val key = it.next(); val x = io.optJSONObject(key) ?: continue
                    indices += HistIndex(key, x.optString("name", key), num(x, "close"), num(x, "changePct") ?: num(x, "change"), num(x, "amount"))
                }
            }
            is JSONArray -> for (i in 0 until io.length()) {
                val x = io.optJSONObject(i) ?: continue
                indices += HistIndex(x.optString("code", x.optString("symbol", i.toString())), x.optString("name", "指数"), num(x, "close"), num(x, "changePct") ?: num(x, "change"), num(x, "amount"))
            }
        }
        val breadth = m?.optJSONObject("breadth")
        return HistMarket(
            date = date,
            indices = indices,
            totalAmount = num(m, "totalAmount") ?: num(m, "marketAmount") ?: num(m, "amount"),
            up = int(m, "up") ?: int(m, "advance") ?: int(breadth, "up"),
            down = int(m, "down") ?: int(m, "decline") ?: int(breadth, "down"),
            flat = int(m, "flat") ?: int(breadth, "flat"),
            limitUp = int(m, "limitUp"),
            limitDown = int(m, "limitDown"),
            medianChange = num(m, "medianChange") ?: num(m, "medianChangePct"),
            ma5Breadth = num(m, "ma5Breadth") ?: num(breadth, "ma5"),
            ma20Breadth = num(m, "ma20Breadth") ?: num(breadth, "ma20"),
            ma60Breadth = num(m, "ma60Breadth") ?: num(breadth, "ma60"),
            industry = parseBoards(h?.optJSONArray("industry"), "industry"),
            concept = parseBoards(h?.optJSONArray("concept"), "concept"),
            source = m?.optString("dataSource")?.takeIf { it.isNotBlank() } ?: m?.optString("source")?.takeIf { it.isNotBlank() },
            availableAt = m?.optString("availableAt")?.takeIf { it.isNotBlank() },
            backfilled = m?.optBoolean("backfilled", false) == true
        )
    }

    private fun parseBoards(a: JSONArray?, type: String): List<HistBoard> {
        if (a == null) return emptyList()
        return (0 until a.length()).mapNotNull { i ->
            val x = a.optJSONObject(i) ?: return@mapNotNull null
            val name = x.optString("name").takeIf { it.isNotBlank() } ?: return@mapNotNull null
            val up = int(x, "up"); val down = int(x, "down"); val flat = int(x, "flat")
            val breadth = num(x, "breadthPct") ?: run {
                val total = (up ?: 0) + (down ?: 0) + (flat ?: 0)
                if (total > 0) (up ?: 0).toDouble() / total * 100.0 else null
            }
            HistBoard(
                code = x.optString("boardCode", x.optString("code")), name = name,
                changePct = num(x, "changePct") ?: num(x, "change"), amount = num(x, "amount"),
                up = up, down = down, flat = flat, breadthPct = breadth,
                mainNetFlow = num(x, "mainNetFlow") ?: num(x, "flow"), mainFlowPct = num(x, "mainFlowPct") ?: num(x, "flowPct"),
                rs5 = num(x, "RS5") ?: num(x, "rs5"), rs20 = num(x, "20日相对强弱") ?: num(x, "rs20"), rs60 = num(x, "60日相对强弱") ?: num(x, "rs60"),
                mta = x.optString("多周期趋势一致性").takeIf { it.isNotBlank() } ?: x.optString("mta").takeIf { it.isNotBlank() },
                confidence = x.optString("confidence").takeIf { it.isNotBlank() }
            )
        }
    }

    private fun num(o: JSONObject?, key: String): Double? {
        if (o == null) return null
        val v = o.opt(key)
        return when (v) { null, JSONObject.NULL -> null; is Number -> v.toDouble(); else -> v.toString().toDoubleOrNull() }
    }
    private fun int(o: JSONObject?, key: String): Int? = num(o, key)?.toInt()

    private fun getText(url: String): String {
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = 8000; c.readTimeout = 8000
        c.setRequestProperty("User-Agent", "Mozilla/5.0 AStockStrategy/0.7")
        c.setRequestProperty("Cache-Control", "no-cache")
        c.connect()
        try {
            if (c.responseCode !in 200..299) error("HTTP ${c.responseCode}")
            return c.inputStream.bufferedReader().use { it.readText() }
        } finally { c.disconnect() }
    }
}
