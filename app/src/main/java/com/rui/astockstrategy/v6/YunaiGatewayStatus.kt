package com.rui.astockstrategy.v6

import androidx.compose.runtime.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

private data class YunaiGatewayState(
    val configured: Boolean,
    val connected: Boolean,
    val endpointCount: Int,
    val openapiState: String?,
    val marketStatusConnected: Boolean,
    val checkedAt: String?
)

@Composable
fun YunaiGatewayStatusLine() {
    var state by remember { mutableStateOf<YunaiGatewayState?>(null) }
    LaunchedEffect(Unit) {
        state = runCatching { fetchYunaiGatewayState() }.getOrNull()
    }
    val s = state
    val label = when {
        s == null -> "读取中"
        !s.configured -> "等待安全令牌"
        s.connected && s.endpointCount > 0 -> "已连接 · 已发现 ${s.endpointCount} 个接口"
        s.connected -> "已连接 · 市场状态已启用"
        else -> "连接异常，继续使用备用源"
    }
    Key("Yunai Quant API", label)
    if (s?.configured == true) {
        Key("Yunai市场状态", if (s.marketStatusConnected) "已启用" else "未启用")
        if (!s.openapiState.isNullOrBlank()) Key("Yunai接口发现", s.openapiState)
    }
}

private suspend fun fetchYunaiGatewayState(): YunaiGatewayState = withContext(Dispatchers.IO) {
    val url = "https://raw.githubusercontent.com/cskjin940509-ops/cskjin/main/astock_gateway/latest.json?t=${System.currentTimeMillis()}"
    val c = URL(url).openConnection() as HttpURLConnection
    c.connectTimeout = 8000
    c.readTimeout = 8000
    c.setRequestProperty("User-Agent", "Mozilla/5.0 AStockStrategy/1.3")
    c.setRequestProperty("Cache-Control", "no-cache")
    c.connect()
    try {
        if (c.responseCode !in 200..299) error("HTTP ${c.responseCode}")
        val root = JSONObject(c.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() })
        val y = root.optJSONObject("yunai")
        val market = y?.optJSONObject("marketStatus")
        YunaiGatewayState(
            configured = y?.optBoolean("configured", false) ?: false,
            connected = y?.optBoolean("connected", false) ?: false,
            endpointCount = y?.optInt("endpointCount", 0) ?: 0,
            openapiState = y?.optString("openapiState")?.takeIf { it.isNotBlank() },
            marketStatusConnected = market?.optBoolean("connected", false) ?: false,
            checkedAt = market?.optString("checkedAt")?.takeIf { it.isNotBlank() }
        )
    } finally {
        c.disconnect()
    }
}
