from pathlib import Path

p = Path('app/src/main/java/com/rui/astockstrategy/v6/ExecutionPanel.kt')
s = p.read_text(encoding='utf-8')
start = s.find('private suspend fun fetchExecutionSnapshot(): ExecSnapshot? = withContext(Dispatchers.IO) {')
end = s.find('\nprivate fun n(o: JSONObject, key: String): Double? {', start)
if start < 0 or end < 0:
    raise SystemExit('execution snapshot parser markers not found')

replacement = r'''private fun compatPct(v: Double?): Double? {
    if (v == null) return null
    return if (kotlin.math.abs(v) <= 1.5) v * 100.0 else v
}

private fun compatSignalLabel(signal: JSONObject?): String {
    val label = signal?.optString("label")?.takeIf { it.isNotBlank() }
    if (label != null && !label.matches(Regex("[A-Z_]+"))) return label
    return when (signal?.optString("state")?.uppercase()) {
        "WAIT_OPEN", "PREOPEN" -> "等待开盘"
        "BUY_ZONE", "BUY", "ACTIONABLE" -> "介入候选"
        "WAIT_PULLBACK", "PULLBACK" -> "等待回踩"
        "WAIT_STABILIZE", "STABILIZE" -> "等待企稳"
        "OBSERVE", "WATCH" -> "观察确认"
        "NO_ENTRY", "SKIP" -> "暂不介入"
        "HOLD" -> "持有观察"
        "REDUCE" -> "考虑减仓"
        "TAKE_PROFIT" -> "分批止盈"
        "EXIT", "SELL", "STOP" -> "保护性离场"
        else -> label ?: "观察"
    }
}

private fun compatPhase(v: String): String = when (v.uppercase()) {
    "PREOPEN" -> "盘前"
    "OPEN", "MORNING" -> "上午连续竞价"
    "LUNCH" -> "午间休市"
    "AFTERNOON" -> "下午连续竞价"
    "TAIL", "TAIL_LIVE" -> "尾盘连续竞价"
    "CLOSING_AUCTION" -> "收盘集合竞价"
    "CLOSED", "AFTERHOURS" -> "已收盘"
    else -> v.ifBlank { "交易辅助" }
}

private suspend fun fetchExecutionSnapshot(): ExecSnapshot? = withContext(Dispatchers.IO) {
    val c = URL("$EXEC_URL?t=${System.currentTimeMillis()}").openConnection() as HttpURLConnection
    c.connectTimeout = 8000
    c.readTimeout = 8000
    c.setRequestProperty("User-Agent", "Mozilla/5.0 AStockStrategy-Execution/2.5")
    c.setRequestProperty("Cache-Control", "no-cache")
    try {
        if (c.responseCode !in 200..299) return@withContext null
        val root = JSONObject(c.inputStream.bufferedReader().use { it.readText() })
        val rows = mutableListOf<ExecStock>()

        // Current 5-minute execution-assistant schema: stocks + ranking.
        val stocksObj = root.optJSONObject("stocks")
        if (stocksObj != null && stocksObj.length() > 0) {
            val ranking = root.optJSONArray("ranking")
            val codes = mutableListOf<String>()
            if (ranking != null) {
                for (i in 0 until ranking.length()) ranking.optString(i).takeIf { it.isNotBlank() }?.let(codes::add)
            }
            if (codes.isEmpty()) {
                val it = stocksObj.keys()
                while (it.hasNext()) codes.add(it.next())
            }
            codes.forEach { code ->
                val x = stocksObj.optJSONObject(code) ?: return@forEach
                rows.add(ExecStock(
                    code = code,
                    name = x.optString("name", code),
                    sector = x.optString("sector").takeIf { it.isNotBlank() },
                    source = x.optString("source").takeIf { it.isNotBlank() },
                    entryScore = n(x, "entryScore"),
                    entryAction = x.optString("entryAction", "观察"),
                    entryReason = x.optString("entryReason").takeIf { it.isNotBlank() },
                    holdingAction = x.optString("holdingAction").takeIf { it.isNotBlank() },
                    holdingReason = x.optString("holdingReason").takeIf { it.isNotBlank() },
                    price = n(x, "price"), changePct = n(x, "changePct"), dayHigh = n(x, "dayHigh"), dayLow = n(x, "dayLow"),
                    dayRangePct = compatPct(n(x, "dayRangePct")), rangePositionPct = n(x, "rangePositionPct"), vwap = n(x, "vwap"),
                    entryZoneLow = n(x, "entryZoneLow"), entryZoneHigh = n(x, "entryZoneHigh"), riskPct = n(x, "riskPct"),
                    protectiveStop = n(x, "protectiveStop"), target1R = n(x, "target1R"), target2R = n(x, "target2R"),
                    mainFlowPct = n(x, "mainFlowPct"), yunaiLargeNetInflow = n(x, "yunaiLargeNetInflow"),
                    firstActionableAt = x.optString("firstActionableAt").takeIf { it.isNotBlank() }, firstActionablePrice = n(x, "firstActionablePrice"),
                    mfePct = n(x, "maxFavorablePctAfterSignal"), maePct = n(x, "maxAdversePctAfterSignal"),
                    bestObservedTime = x.optString("bestObservedTimeAfterSignal").takeIf { it.isNotBlank() },
                    metricPrecision = x.optString("postSignalMetricPrecision").takeIf { it.isNotBlank() },
                ))
            }
        } else {
            // Pre-open / legacy execution schema: officialCandidates array.
            val candidates = root.optJSONArray("officialCandidates")
            if (candidates != null) {
                for (i in 0 until candidates.length()) {
                    val x = candidates.optJSONObject(i) ?: continue
                    val code = x.optString("code").takeIf { it.isNotBlank() } ?: continue
                    val q = x.optJSONObject("quote")
                    val ds = x.optJSONObject("dayStats")
                    val signal = x.optJSONObject("signal")
                    val paper = x.optJSONObject("paperPosition")
                    val price = n(x, "price") ?: q?.let { n(it, "price") }
                    val high = n(x, "dayHigh") ?: ds?.let { n(it, "high") } ?: q?.let { n(it, "high") }
                    val low = n(x, "dayLow") ?: ds?.let { n(it, "low") } ?: q?.let { n(it, "low") }
                    val rangePos = if (price != null && high != null && low != null && high > low) (price - low) / (high - low) * 100.0 else null
                    rows.add(ExecStock(
                        code = code,
                        name = x.optString("name", code),
                        sector = x.optString("sector").takeIf { it.isNotBlank() },
                        source = x.optString("source").takeIf { it.isNotBlank() } ?: "Official",
                        entryScore = signal?.let { n(it, "entryScore") } ?: n(x, "entryScore") ?: n(x, "score"),
                        entryAction = compatSignalLabel(signal),
                        entryReason = signal?.optString("reason")?.takeIf { it.isNotBlank() } ?: x.optString("entryReason").takeIf { it.isNotBlank() },
                        holdingAction = paper?.optString("holdingAction")?.takeIf { it.isNotBlank() } ?: x.optString("holdingAction").takeIf { it.isNotBlank() },
                        holdingReason = paper?.optString("holdingReason")?.takeIf { it.isNotBlank() } ?: x.optString("holdingReason").takeIf { it.isNotBlank() },
                        price = price,
                        changePct = n(x, "changePct") ?: q?.let { n(it, "changePct") },
                        dayHigh = high,
                        dayLow = low,
                        dayRangePct = compatPct(n(x, "dayRangePct") ?: ds?.let { n(it, "rangePct") }),
                        rangePositionPct = n(x, "rangePositionPct") ?: rangePos,
                        vwap = n(x, "vwap") ?: signal?.let { n(it, "vwap") },
                        entryZoneLow = n(x, "entryZoneLow") ?: signal?.let { n(it, "zoneLow") },
                        entryZoneHigh = n(x, "entryZoneHigh") ?: signal?.let { n(it, "zoneHigh") },
                        riskPct = n(x, "riskPct") ?: signal?.let { n(it, "riskPct") },
                        protectiveStop = n(x, "protectiveStop") ?: paper?.let { n(it, "protectiveStop") },
                        target1R = n(x, "target1R") ?: paper?.let { n(it, "target1R") },
                        target2R = n(x, "target2R") ?: paper?.let { n(it, "target2R") },
                        mainFlowPct = n(x, "mainFlowPct"),
                        yunaiLargeNetInflow = n(x, "yunaiLargeNetInflow"),
                        firstActionableAt = x.optString("firstActionableAt").takeIf { it.isNotBlank() } ?: signal?.optString("actionableAt")?.takeIf { it.isNotBlank() },
                        firstActionablePrice = n(x, "firstActionablePrice") ?: signal?.let { n(it, "actionablePrice") },
                        mfePct = n(x, "maxFavorablePctAfterSignal") ?: paper?.let { n(it, "mfePct") },
                        maePct = n(x, "maxAdversePctAfterSignal") ?: paper?.let { n(it, "maePct") },
                        bestObservedTime = x.optString("bestObservedTimeAfterSignal").takeIf { it.isNotBlank() },
                        metricPrecision = x.optString("postSignalMetricPrecision").takeIf { it.isNotBlank() },
                    ))
                }
            }
        }

        val date = root.optString("date").takeIf { it.isNotBlank() }
            ?: root.optString("marketDate").takeIf { it.isNotBlank() }
            ?: LocalDate.now(java.time.ZoneId.of("Asia/Shanghai")).toString()
        ExecSnapshot(
            date,
            root.optString("generatedAt"),
            compatPhase(root.optString("phase", "交易辅助")),
            root.optInt("refreshIntervalMin", 5),
            rows
        )
    } finally { c.disconnect() }
}
'''

s = s[:start] + replacement + s[end:]
p.write_text(s, encoding='utf-8')

# Final compatibility version bump after v2.4 trade journal patch.
g = Path('app/build.gradle.kts')
gs = g.read_text(encoding='utf-8')
gs = gs.replace('versionCode = 26', 'versionCode = 27')
gs = gs.replace('versionName = "2.4.0"', 'versionName = "2.5.0"')
if 'versionName = "2.5.0"' not in gs:
    raise SystemExit('v2.5 version bump failed')
g.write_text(gs, encoding='utf-8')

assert 'officialCandidates' in p.read_text(encoding='utf-8')
assert 'stocksObj' in p.read_text(encoding='utf-8')
print('execution schema compatibility enabled')
