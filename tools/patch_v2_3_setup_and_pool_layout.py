from pathlib import Path


def replace_between(text: str, start: str, end: str, replacement: str) -> str:
    a=text.find(start)
    if a<0: raise SystemExit(f'start marker not found: {start}')
    b=text.find(end,a+len(start))
    if b<0: raise SystemExit(f'end marker not found: {end}')
    return text[:a]+replacement.rstrip()+'\n\n'+text[b:]

p=Path('app/src/main/java/com/rui/astockstrategy/v6/V6Activity.kt')
s=p.read_text(encoding='utf-8')

# Final pool selector: two fixed-height rows, four equal weighted cells each.
selector=r'''@Composable
fun PoolSelector(value: String, onChange: (String) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
        Text("基础与单因子确认", fontSize = 10.sp, color = Muted, fontWeight = FontWeight.SemiBold)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            listOf("B0" to "基础", "B1" to "两融", "B2" to "指数基金", "B3" to "主力").forEach { (key, label) ->
                UniformPoolCell(key, label, value == key, Modifier.weight(1f)) { onChange(key) }
            }
        }
        Text("多联合确认", fontSize = 10.sp, color = Muted, fontWeight = FontWeight.SemiBold)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            listOf("B12" to "融+基金", "B13" to "融+主力", "B23" to "基金+主力", "B4" to "综合").forEach { (key, label) ->
                UniformPoolCell(key, label, value == key, Modifier.weight(1f)) { onChange(key) }
            }
        }
        Text("当前：${poolTitle(value)}", fontSize = 10.sp, color = Blue)
    }
}

@Composable
fun UniformPoolCell(key: String, label: String, selected: Boolean, modifier: Modifier, onClick: () -> Unit) {
    Surface(
        modifier = modifier.height(50.dp).clickable(onClick = onClick),
        color = if (selected) SoftBlue else Color.White,
        shape = RoundedCornerShape(11.dp),
        tonalElevation = if (selected) 1.dp else 0.dp
    ) {
        Column(
            Modifier.fillMaxSize(),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Text(key, fontSize = 10.sp, fontWeight = FontWeight.Bold, color = if (selected) Blue else Ink)
            Text(label, fontSize = 8.sp, color = Muted, maxLines = 1)
        }
    }
}'''
s=replace_between(s,'@Composable\nfun PoolSelector(','@Composable\nfun Choice(',selector)

# Existing v2.2 execution panel is primary. Historical-shape alternatives only appear
# when backend finds them; this panel therefore stays hidden when not needed.
if 'ShapeSetupPanel()' not in s:
    needle='item { ExecutionPanel() }'
    if needle not in s: raise SystemExit('ExecutionPanel insertion point not found')
    s=s.replace(needle,needle+'\n        item { ShapeSetupPanel() }',1)

p.write_text(s,encoding='utf-8')

g=Path('app/build.gradle.kts')
gs=g.read_text(encoding='utf-8')
gs=gs.replace('versionCode = 24','versionCode = 25')
gs=gs.replace('versionName = "2.2.0"','versionName = "2.3.0"')
g.write_text(gs,encoding='utf-8')
