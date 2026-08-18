from pathlib import Path


# Remove legacy activities that conflict with the current app entrypoint.
for file_name in [
    "app/src/main/java/com/rui/astockstrategy/V04Activity.kt",
    "app/src/main/java/com/rui/astockstrategy/v5/V5Activity.kt",
]:
    Path(file_name).unlink(missing_ok=True)


activity_path = Path("app/src/main/java/com/rui/astockstrategy/v6/V6Activity.kt")
activity = activity_path.read_text(encoding="utf-8")

# Historical market replay entry.
history_needle = '''        item { CardBlock { Key("日期", snap.date); Key("状态", snap.status); Key("Regime", snap.regime); Key("主线", snap.mainlines.joinToString(" / ").ifBlank { "—" }) } }'''
history_replacement = '''        item { CardBlock { Key("日期", snap.date); Key("状态", zhStatus(snap.status)); Key("市场状态", snap.regime); Key("主线", snap.mainlines.joinToString(" / ").ifBlank { "—" }) } }\n        item { HistoricalMarketReplay(snap.date) }\n        item { Title("策略回顾") }'''
if "HistoricalMarketReplay(snap.date)" not in activity:
    if history_needle not in activity:
        raise SystemExit("history insertion point not found")
    activity = activity.replace(history_needle, history_replacement, 1)

# Post-close facts first, strategy later. The quant panel keeps the JWT in memory only.
today_old = '''        item {\n            StatusCard(now, quoteOkAt, boardOkAt, s)\n        }\n        item { Title("Intraday Preview（盘中预览）") }\n        item {\n            Notice("盘中只用当前可实时取得的公开行情生成主线候选，不冒充正式 B1/B2/B3/B4。正式 Daily Cohort 收盘后另行冻结。")\n        }'''
today_new = '''        item {\n            StatusCard(now, quoteOkAt, boardOkAt, s)\n        }\n        item { QuantSourcePanel() }\n        if (!marketOpenNow()) {\n            item { PostCloseDashboard(quotes, preview, s) }\n            item { Title("收盘主线预览") }\n            item { Notice("收盘后先展示当天已核验的指数、板块和资金事实；正式每日股票池尚未完成时显示“策略计算中”，不使用昨日名单冒充今天结果。") }\n        } else {\n            item { Title("盘中主线预览") }\n            item { Notice("盘中主线仅使用当前可取得的实时行情计算；两融、ETF申赎等非实时因子不会伪装成实时数据。") }\n        }'''
if "QuantSourcePanel()" not in activity:
    if today_old not in activity:
        raise SystemExit("today insertion point not found")
    activity = activity.replace(today_old, today_new, 1)

# Direct source first; GitHub gateway fallback second.
activity = activity.replace(
    '''            runCatching {\n                val ind = DataApi.fetchBoards("industry")\n                val con = DataApi.fetchBoards("concept")\n                ind to con\n            }''',
    '''            runCatching { ResilientDataApi.fetchBoardsPair() }''',
)
activity = activity.replace(
    "runCatching { DataApi.fetchQuotes(symbols) }",
    "runCatching { ResilientDataApi.fetchQuotes(symbols) }",
)

# Imports needed by the secure runtime-token panel.
activity = activity.replace(
    "import androidx.compose.ui.text.font.FontWeight",
    "import androidx.compose.ui.text.font.FontWeight\nimport androidx.compose.ui.text.input.PasswordVisualTransformation",
)
activity = activity.replace(
    "import kotlinx.coroutines.withContext",
    "import kotlinx.coroutines.withContext\nimport kotlinx.coroutines.launch",
)

# Data source diagnostics.
status_line = '''            Key("盘中主线", if (marketOpenNow()) "LIVE Preview" else "Close Preview")'''
status_new = '''            Key("盘中主线", if (marketOpenNow()) "实时预览" else "收盘预览")\n            Key("quant.yunai", ResilientDataApi.quantStatus)\n            Key("行情来源", ResilientDataApi.quoteSource)\n            Key("板块来源", ResilientDataApi.boardSource)'''
activity = activity.replace(status_line, status_new)

# Runtime token input. The token is not persisted and is removed from the text field after success.
panel_marker = "@Composable\nfun PreviewRow(p: PreviewSector) {"
panel = '''@Composable
fun QuantSourcePanel() {
    var token by remember { mutableStateOf("") }
    var message by remember { mutableStateOf(ResilientDataApi.quantStatus) }
    var testing by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    CardBlock {
        Text("quant.yunai 数据源自检", fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(5.dp))
        Text("令牌只保存在当前应用进程内，重启后自动清除，不写入 APK、日志或历史快照。", fontSize = 10.sp, color = Muted)
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(
            value = token,
            onValueChange = { token = it },
            modifier = Modifier.fillMaxWidth(),
            label = { Text("Bearer JWT") },
            placeholder = { Text("可粘贴 Bearer 开头的完整令牌") },
            visualTransformation = PasswordVisualTransformation(),
            singleLine = true,
            enabled = !testing
        )
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            Button(
                enabled = token.isNotBlank() && !testing,
                onClick = {
                    scope.launch {
                        testing = true
                        message = ResilientDataApi.configureAndTestQuant(token)
                        if (ResilientDataApi.quantEnabled) token = ""
                        testing = false
                    }
                }
            ) { Text(if (testing) "正在验证" else "验证并启用") }
            TextButton(
                enabled = ResilientDataApi.quantEnabled && !testing,
                onClick = {
                    ResilientDataApi.clearQuant()
                    message = ResilientDataApi.quantStatus
                }
            ) { Text("停用") }
        }
        Text(message, fontSize = 10.sp, color = if (ResilientDataApi.quantEnabled) Down else Amber)
    }
}

'''
if "fun QuantSourcePanel()" not in activity:
    if panel_marker not in activity:
        raise SystemExit("quant panel marker not found")
    activity = activity.replace(panel_marker, panel + panel_marker, 1)

# Chinese financial terminology in user-facing UI only.
for old, new in {
    "Data Status（数据状态）": "数据状态",
    "实时行情和策略快照分开显示": "实时行情、板块数据与策略快照分层显示",
    "Intraday Preview（盘中预览）": "盘中主线预览",
    "Latest Official / Snapshot": "最新正式策略快照",
    "B4 Live Monitor（实时跟踪）": "B4组合实时跟踪",
    "Mainline Preview": "主线预览",
    "Momentum": "动量强度",
    "Breadth": "上涨扩散度",
    "Flow": "资金强度",
    "Official Snapshot": "正式策略快照",
    "Market Alpha": "市场超额收益",
    "Industry Alpha": "行业超额收益",
    "MFE": "最大有利涨幅",
    "MAE": "最大不利跌幅",
    "Trend Survival": "趋势存续期",
}.items():
    activity = activity.replace(old, new)

activity = activity.replace(
    'item { Title("实时${type}热力图") }',
    'item { Title(if (marketOpenNow()) "实时${type}热力图" else "收盘${type}热力图") }',
)

# Validate provider timestamp; never expose raw dirty values such as 161495.
activity = activity.replace(
    "quoteTime = f.getOrNull(30)",
    "quoteTime = normalizeQuoteTime(f.getOrNull(30))",
)
helper_marker = "fun breadth(b: Board): Double {"
helper = '''fun normalizeQuoteTime(raw: String?): String? {\n    val v = raw?.trim().orEmpty()\n    if (!Regex("\\\\d{14}").matches(v)) return null\n    return runCatching {\n        LocalDateTime.parse(v, DateTimeFormatter.ofPattern("yyyyMMddHHmmss"))\n            .format(DateTimeFormatter.ofPattern("HH:mm:ss"))\n    }.getOrNull()\n}\n\nfun zhStatus(v: String?): String = when (v?.lowercase()) {\n    "official" -> "正式"\n    "preview" -> "预览"\n    else -> v ?: "未知"\n}\n\n'''
if "fun normalizeQuoteTime" not in activity:
    if helper_marker not in activity:
        raise SystemExit("breadth helper marker not found")
    activity = activity.replace(helper_marker, helper + helper_marker, 1)

activity = activity.replace('return "行情 OFFLINE"', 'return "行情未连接"')
activity = activity.replace('return "行情 STALE ${age}s"', 'return "行情已过期 ${age}秒"')
activity = activity.replace('"行情 LIVE ${age}s"', '"行情实时 ${age}秒"')
activity = activity.replace(
    '"行情 CLOSED ${quoteTime?.takeLast(6) ?: "已收盘"}"',
    '"行情已收盘 ${quoteTime ?: ""}"',
)
activity = activity.replace('"LIVE", "STALE"', '"实时", "已过期"')
activity = activity.replace('return "OFFLINE"', 'return "未连接"')
activity = activity.replace('q?.quoteTime?.let { "行情 $it" }', 'q?.quoteTime?.let { "行情时间 $it" }')
activity = activity.replace('"无时间戳"', '"行情时间不可用"')
activity = activity.replace(
    'EmptyCard("尚未读取到正式策略快照")',
    'EmptyCard("正式策略尚未同步；行情与板块数据仍独立可用")',
)
activity = activity.replace('EmptyCard("暂无 Official Snapshot")', 'EmptyCard("正式策略尚未同步")')

# Improve direct public-source compatibility on Android.
http_old = '''        c.setRequestProperty("User-Agent", "Mozilla/5.0 AStockStrategy/0.6")\n        c.setRequestProperty("Cache-Control", "no-cache")'''
http_new = '''        c.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 Chrome/140 Mobile Safari/537.36")\n        c.setRequestProperty("Accept", "*/*")\n        c.setRequestProperty("Cache-Control", "no-cache")\n        if (url.contains("gtimg.cn")) c.setRequestProperty("Referer", "https://gu.qq.com/")\n        if (url.contains("eastmoney.com")) c.setRequestProperty("Referer", "https://quote.eastmoney.com/")'''
activity = activity.replace(http_old, http_new)
activity_path.write_text(activity, encoding="utf-8")


# Add quant.yunai as the preferred stock quote source after runtime authentication.
gateway_path = Path("app/src/main/java/com/rui/astockstrategy/v6/GatewayFallback.kt")
gateway = gateway_path.read_text(encoding="utf-8")
gateway = gateway.replace(
    "import org.json.JSONObject",
    "import org.json.JSONArray\nimport org.json.JSONObject",
)
gateway = gateway.replace(
    "import java.net.URL",
    "import java.net.URL\nimport java.time.Instant\nimport java.time.ZoneId\nimport java.time.format.DateTimeFormatter",
)

old_fetch_quotes = '''    suspend fun fetchQuotes(symbols: List<String>): Map<String, Quote> {\n        val direct = runCatching { DataApi.fetchQuotes(symbols) }.getOrNull()\n        if (!direct.isNullOrEmpty()) {\n            quoteSource = "腾讯行情"\n            return direct\n        }\n        val fallback = fetchGatewayQuotes(symbols)\n        quoteSource = if (fallback.isNotEmpty()) "备用市场快照" else "行情源不可用"\n        return fallback\n    }'''
new_fetch_quotes = '''    suspend fun fetchQuotes(symbols: List<String>): Map<String, Quote> {
        if (quantEnabled) {
            val quantQuotes = runCatching { fetchQuantQuotes(symbols) }
                .onFailure { quantStatus = "连接异常 · ${safeError(it)}" }
                .getOrDefault(emptyMap())
            if (quantQuotes.isNotEmpty()) {
                val missing = symbols.filterNot { it in quantQuotes }
                val publicFallback = if (missing.isEmpty()) emptyMap() else
                    runCatching { DataApi.fetchQuotes(missing) }.getOrDefault(emptyMap())
                quoteSource = if (publicFallback.isEmpty()) "quant.yunai" else "quant.yunai（股票）+ 腾讯（指数/兜底）"
                return publicFallback + quantQuotes
            }
        }

        val direct = runCatching { DataApi.fetchQuotes(symbols) }.getOrNull()
        if (!direct.isNullOrEmpty()) {
            quoteSource = "腾讯行情"
            return direct
        }
        val fallback = fetchGatewayQuotes(symbols)
        quoteSource = if (fallback.isNotEmpty()) "备用市场快照" else "行情源不可用"
        return fallback
    }'''
if old_fetch_quotes not in gateway:
    raise SystemExit("gateway fetchQuotes marker not found")
gateway = gateway.replace(old_fetch_quotes, new_fetch_quotes, 1)

gateway_state_marker = '''    @Volatile var gatewayGeneratedAt: String? = null\n        private set'''
gateway_state = '''    @Volatile var gatewayGeneratedAt: String? = null
        private set
    @Volatile var quantStatus: String = "未启用"
        private set
    @Volatile var quantEnabled: Boolean = false
        private set
    @Volatile private var quantToken: String? = null'''
if gateway_state_marker not in gateway:
    raise SystemExit("gateway state marker not found")
gateway = gateway.replace(gateway_state_marker, gateway_state, 1)

gateway_method_marker = "    suspend fun fetchBoardsPair(): Pair<List<Board>, List<Board>> {"
gateway_methods = '''    suspend fun configureAndTestQuant(rawToken: String): String {
        val normalized = rawToken.trim()
            .replace(Regex("^Bearer\\s+", RegexOption.IGNORE_CASE), "")
            .trim()
        if (normalized.isBlank()) return "请输入有效令牌"

        quantToken = normalized
        quantEnabled = false
        quantStatus = "正在验证"
        return runCatching {
            val market = fetchQuantMarketStatus()
            val probe = fetchQuantQuotes(listOf("sz000001"))
            require(probe.isNotEmpty()) { "实时行情返回为空" }
            quantEnabled = true
            quantStatus = "已连接 · $market"
            quoteSource = "quant.yunai"
            quantStatus
        }.getOrElse {
            quantToken = null
            quantEnabled = false
            quantStatus = "连接失败 · ${safeError(it)}"
            quantStatus
        }
    }

    fun clearQuant() {
        quantToken = null
        quantEnabled = false
        quantStatus = "未启用"
    }

    private suspend fun fetchQuantQuotes(symbols: List<String>): Map<String, Quote> = withContext(Dispatchers.IO) {
        val indexSymbols = setOf("sh000001", "sz399006", "sh000688", "sh000300", "sh000852")
        val appByCode = symbols
            .filterNot { it in indexSymbols }
            .associateBy { it.removePrefix("sh").removePrefix("sz") }
        if (appByCode.isEmpty()) return@withContext emptyMap()

        val body = JSONObject().put("symbols", JSONArray(appByCode.keys.toList())).toString()
        val root = quantRequest(
            method = "POST",
            path = "/api/v1/quantitative/quotes/real-time-quotes",
            body = body
        ) as JSONObject
        val out = linkedMapOf<String, Quote>()
        val keys = root.keys()
        while (keys.hasNext()) {
            val code = keys.next()
            val appSymbol = appByCode[code] ?: continue
            val item = root.optJSONObject(code) ?: continue
            val rate = n(item, "changeRate")?.times(100.0)
            val timeMs = item.optLong("latestTime", 0L)
            out[appSymbol] = Quote(
                symbol = appSymbol,
                name = item.optString("name").takeIf { it.isNotBlank() } ?: code,
                code = code,
                price = n(item, "latestPrice") ?: n(item, "close"),
                prev = n(item, "preClose"),
                change = rate,
                high = n(item, "high"),
                low = n(item, "low"),
                amount = n(item, "amount"),
                quoteTime = formatEpochTime(timeMs)
            )
        }
        out
    }

    private suspend fun fetchQuantMarketStatus(): String = withContext(Dispatchers.IO) {
        val result = quantRequest(
            method = "GET",
            path = "/api/v1/quantitative/quotes/market-status?market=CN&lang=zh_CN",
            body = null
        ) as JSONArray
        val cn = (0 until result.length())
            .mapNotNull { result.optJSONObject(it) }
            .firstOrNull { it.optString("market") == "CN" }
            ?: result.optJSONObject(0)
        val state = cn?.optString("status").orEmpty()
        when (state) {
            "TRADING" -> "A股交易中"
            "MIDDLE_CLOSE" -> "A股午间休市"
            "CLOSED", "AFTER_HOURS" -> "A股已收盘"
            "NOT_YET_OPEN" -> "A股未开盘"
            else -> cn?.optString("marketStatus").takeUnless { it.isNullOrBlank() } ?: "A股状态已返回"
        }
    }

    private fun quantRequest(method: String, path: String, body: String?): Any {
        val token = quantToken ?: error("令牌未配置")
        val url = "https://quant.yunai.com.cn/quant-market$path"
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.requestMethod = method
        connection.connectTimeout = 10000
        connection.readTimeout = 10000
        connection.setRequestProperty("Authorization", "Bearer $token")
        connection.setRequestProperty("Accept", "application/json")
        connection.setRequestProperty("User-Agent", "AStockStrategy/1.1 Android")
        if (body != null) {
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
        }
        connection.connect()
        try {
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (status !in 200..299) error("HTTP $status")
            val trimmed = text.trim()
            return if (trimmed.startsWith("[")) JSONArray(trimmed) else JSONObject(trimmed)
        } finally {
            connection.disconnect()
        }
    }

    private fun formatEpochTime(value: Long): String? {
        if (value <= 0L) return null
        return runCatching {
            Instant.ofEpochMilli(value)
                .atZone(ZoneId.of("Asia/Shanghai"))
                .format(DateTimeFormatter.ofPattern("HH:mm:ss"))
        }.getOrNull()
    }

    private fun safeError(error: Throwable): String = when {
        error.message?.startsWith("HTTP ") == true -> error.message.orEmpty()
        else -> error.javaClass.simpleName.ifBlank { "请求失败" }
    }

'''
if gateway_method_marker not in gateway:
    raise SystemExit("gateway method marker not found")
gateway = gateway.replace(gateway_method_marker, gateway_methods + gateway_method_marker, 1)
gateway_path.write_text(gateway, encoding="utf-8")


# Historical market replay fixes and Chinese terminology.
history_path = Path("app/src/main/java/com/rui/astockstrategy/v6/HistoricalReplay.kt")
history = history_path.read_text(encoding="utf-8")
history = history.replace(
    '"该日$title热力图尚未冻结/回填。不会显示今天的实时板块数据。"',
    '"该日${title}热力图尚未冻结/回填。不会显示今天的实时板块数据。"',
)
for old, new in {
    "Historical Market Replay（历史市场回放）": "历史市场回放",
    "Backfill（历史回填）": "历史回填",
    "marketSnapshot / boardHeatmap": "市场快照 / 板块热力图",
    "RS20": "20日相对强弱",
    "MTA ": "多周期趋势 ",
}.items():
    history = history.replace(old, new)
history = history.replace(
    "历史数据读取失败：$error。不会拿当前实时行情冒充历史。",
    "历史数据源读取失败（$error）。不会拿当前行情冒充历史。",
)
history = history.replace(
    "$date 尚未保存 市场快照 / 板块热力图。后台完成历史回填后这里会自动出现，不需要重装 APK。",
    "$date 的市场快照和板块热力图尚未同步；后台补齐后会自动出现。",
)
history = history.replace(
    '"该日${title}热力图尚未冻结/回填。不会显示今天的实时板块数据。"',
    '"该日${title}热力图数据尚未同步，不会拿今天行情冒充历史。"',
)
history_path.write_text(history, encoding="utf-8")


# Post-close screen Chinese terminology.
post_close_path = Path("app/src/main/java/com/rui/astockstrategy/v6/PostCloseDashboard.kt")
post_close = post_close_path.read_text(encoding="utf-8")
for old, new in {
    "Post-close Market Snapshot（收盘市场截面）": "收盘市场截面",
    "Official Daily Cohort": "正式每日股票池",
    "Breadth": "上涨扩散度",
    "Score ": "综合强度 ",
    "Confirmed Candidate": "强势候选",
    "Candidate": "候选",
    "Observe": "观察",
}.items():
    post_close = post_close.replace(old, new)
post_close_path.write_text(post_close, encoding="utf-8")


# Version.
gradle_path = Path("app/build.gradle.kts")
gradle = gradle_path.read_text(encoding="utf-8")
gradle = gradle.replace("versionCode = 7", "versionCode = 12")
gradle = gradle.replace('versionName = "0.7.0"', 'versionName = "1.1.0"')
gradle_path.write_text(gradle, encoding="utf-8")

