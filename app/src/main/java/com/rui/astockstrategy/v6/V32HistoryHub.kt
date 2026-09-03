package com.rui.astockstrategy.v6

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private val H32Blue = Color(0xFF3557D4)
private val H32Muted = Color(0xFF747B8D)

@Composable
fun HistoryHub32(
    all: List<Snapshot>,
    s: Snapshot?,
    quotes: Map<String, Quote>,
    selectedDate: String?,
    onDate: (String) -> Unit
) {
    val modes = listOf("最新版框架", "证据跟踪", "形态实验室")
    var mode by remember { mutableStateOf(modes.first()) }
    Column(Modifier.fillMaxSize()) {
        Surface(color = Color(0xFFF5F7FB)) {
            Column(
                Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp),
                verticalArrangement = Arrangement.spacedBy(7.dp)
            ) {
                Text("历史研究", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                Text("先查看最新版研究准入，再分别审计冻结证据与历史形态；各统计口径互不覆盖。", color = H32Muted, fontSize = 9.sp)
                SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                    modes.forEachIndexed { index, item ->
                        SegmentedButton(
                            selected = mode == item,
                            onClick = { mode = item },
                            shape = SegmentedButtonDefaults.itemShape(index, modes.size),
                            label = { Text(item, fontSize = 10.sp) }
                        )
                    }
                }
            }
        }
        Box(Modifier.fillMaxWidth().weight(1f)) {
            when (mode) {
                "最新版框架" -> FrameworkResearchScreen40(s)
                "证据跟踪" -> HistoryScreen(all, s, quotes, selectedDate, onDate)
                else -> HistoryPatternLabScreen29()
            }
        }
    }
}
