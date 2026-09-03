package com.rui.astockstrategy.v6

import androidx.compose.runtime.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject

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
    Key("云AI量化数据接口", label)
    if (s?.configured == true) {
        Key("云AI量化市场状态", if (s.marketStatusConnected) "已启用" else "未启用")
        if (!s.openapiState.isNullOrBlank()) {
            val discovery = when (s.openapiState.lowercase()) {
                "ready", "ok", "success" -> "已就绪"
                "unavailable", "failed", "error" -> "不可用"
                else -> "已读取"
            }
            Key("云AI量化接口发现", discovery)
        }
    }
}

private suspend fun fetchYunaiGatewayState(): YunaiGatewayState = withContext(Dispatchers.IO) {
        val root = JSONObject(BackendClient.fetchText("astock_gateway/latest.json"))
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
}
