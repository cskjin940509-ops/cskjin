package com.rui.astockstrategy.v6

fun displayStatusZh27(v: String?): String = when (v?.trim()?.lowercase()) {
    null, "" -> "未知"
    "official" -> "正式冻结"
    "preview" -> "盘中预览"
    "tailfinal" -> "尾盘最终"
    "taillive" -> "尾盘滚动"
    "radarlive" -> "全天雷达滚动"
    "radarfinal" -> "全天雷达收盘冻结"
    "ready" -> "已就绪"
    "live" -> "实时"
    "stale" -> "已过期"
    "offline" -> "未连接"
    "closed" -> "已收盘"
    "unknown" -> "未知"
    else -> v ?: "未知"
}

fun displayPoolZh27(v: String): String = when (v) {
    "B0" -> "行情/成交/广度证据"
    "B1" -> "两融证据"
    "B2" -> "ETF一级份额证据"
    "B3" -> "主力或其他资金证据"
    "B4" -> "旧综合标签（兼容）"
    "B12" -> "两融+ETF交叉证据"
    "B13" -> "两融+主力交叉证据"
    "B23" -> "ETF+主力交叉证据"
    "B123" -> "三类资金共同确认"
    "TB0" -> "尾盘基础强度池"
    "TB3" -> "尾盘资金确认池"
    "TailCore" -> "尾盘核心池"
    "EarlyWatch" -> "提前观察池"
    "EarlyEntry" -> "提前介入候选池"
    "Confirming" -> "主线确认中候选池"
    "EstablishedLowChase" -> "已成主线低追高风险池"
    "AvoidChase" -> "禁止追高观察池"
    else -> v
}

fun displayPreviewStateZh27(v: String?): String = when (v) {
    "Confirmed Candidate" -> "确认候选"
    "Candidate" -> "候选"
    "Observe" -> "观察"
    "EMERGING" -> "潜在形成"
    "CONFIRMING" -> "确认中"
    "ESTABLISHED" -> "已成主线"
    "OVERHEATED" -> "过热"
    "FADING" -> "衰退"
    "RADAR" -> "雷达观察"
    else -> displayStatusZh27(v)
}

fun displayHorizonZh27(v: String): String = when (v) {
    "1D" -> "1日"
    "2D" -> "2日"
    "3D" -> "3日"
    "5D" -> "5日"
    "10D" -> "10日"
    "20D" -> "20日"
    "60D" -> "60日"
    else -> v
}

fun displayRegimeZh27(v: String?): String = when (v?.trim()?.lowercase()) {
    null, "", "unknown" -> "未知"
    "risk-on", "risk_on", "riskon" -> "风险偏好上升"
    "risk-off", "risk_off", "riskoff" -> "风险偏好下降"
    "neutral" -> "中性"
    else -> v ?: "未知"
}

fun displayErrorZh27(v: String?): String = when (v) {
    null -> "正常"
    "SocketTimeoutException" -> "请求超时"
    "UnknownHostException" -> "网络解析失败"
    "ConnectException" -> "连接失败"
    "SSLException" -> "安全连接失败"
    else -> "数据请求异常"
}


fun displayChoiceZh27(v: String): String = when (v) {
    "盘中Preview", "盘中预览" -> "盘中预览"
    "Official" -> "正式主线"
    "B0", "B1", "B2", "B3", "B4", "B12", "B13", "B23", "B123", "TB0", "TB3", "TailCore",
    "EarlyWatch", "EarlyEntry", "Confirming", "EstablishedLowChase", "AvoidChase" -> displayPoolZh27(v)
    else -> v
}
