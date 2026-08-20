from pathlib import Path

root = Path('app/src/main/java/com/rui/astockstrategy/v6')
ui = root / 'V32HistoryHub.kt'
ui.write_text(r'''package com.rui.astockstrategy.v6

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
    var mode by remember { mutableStateOf("筛选池跟踪") }
    Column(Modifier.fillMaxSize()) {
        Surface(color = Color(0xFFF5F7FB)) {
            Column(
                Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp),
                verticalArrangement = Arrangement.spacedBy(7.dp)
            ) {
                Text("历史研究", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                Text("筛选池真实批次跟踪与历史形态研究并列保留，二者统计口径互不覆盖。", color = H32Muted, fontSize = 9.sp)
                SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                    listOf("筛选池跟踪", "形态实验室").forEachIndexed { index, item ->
                        SegmentedButton(
                            selected = mode == item,
                            onClick = { mode = item },
                            shape = SegmentedButtonDefaults.itemShape(index, 2),
                            label = { Text(item, fontSize = 10.sp) }
                        )
                    }
                }
            }
        }
        Box(Modifier.fillMaxWidth().weight(1f)) {
            when (mode) {
                "筛选池跟踪" -> HistoryScreen(all, s, quotes, selectedDate, onDate)
                else -> HistoryPatternLabScreen29()
            }
        }
    }
}
''', encoding='utf-8')

v6 = root / 'V6Activity.kt'
s = v6.read_text(encoding='utf-8')
old = 'Tab.HISTORY -> HistoryPatternLabScreen29()'
new = 'Tab.HISTORY -> HistoryHub32(snapshots, active, quotes, selectedDate) { selectedDate = it }'
if old in s:
    s = s.replace(old, new, 1)
elif new not in s:
    raise SystemExit('v3.2 history route anchor missing')
v6.write_text(s, encoding='utf-8')

g = Path('app/build.gradle.kts')
gs = g.read_text(encoding='utf-8')
gs = gs.replace('versionCode = 33', 'versionCode = 34')
gs = gs.replace('versionName = "3.1.0"', 'versionName = "3.2.0"')
if 'versionName = "3.2.0"' not in gs:
    raise SystemExit('v3.2 version bump failed')
g.write_text(gs, encoding='utf-8')

assert ui.exists()
assert 'HistoryHub32(' in v6.read_text(encoding='utf-8')
print('v3.2 restored pool history tracking alongside pattern lab')
