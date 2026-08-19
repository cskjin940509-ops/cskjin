from pathlib import Path

p = Path('app/src/main/java/com/rui/astockstrategy/v6/ExecutionPanel.kt')
s = p.read_text(encoding='utf-8')

# CnZone is intentionally private in V6Activity.kt, so keep the execution panel
# self-contained instead of widening the old file's visibility.
s = s.replace('LocalDate.now(CnZone)', 'LocalDate.now(java.time.ZoneId.of("Asia/Shanghai"))')
s = s.replace('java.time.LocalTime.now(CnZone)', 'java.time.LocalTime.now(java.time.ZoneId.of("Asia/Shanghai"))')

# Avoid Java Iterator.forEachRemaining + MutableList.add method-reference ambiguity.
s = s.replace(
    'stocksObj.keys().forEachRemaining(codes::add)',
    'stocksObj.keys().asSequence().forEach { codes.add(it) }'
)

p.write_text(s, encoding='utf-8')
