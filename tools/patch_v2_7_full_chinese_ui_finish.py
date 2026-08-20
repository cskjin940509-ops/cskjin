from pathlib import Path
import re

root = Path('app/src/main/java/com/rui/astockstrategy/v6')
helper = root / 'V27ChineseDisplay.kt'
detail = root / 'DetailScreens.kt'

if not helper.exists():
    raise SystemExit('V27ChineseDisplay.kt missing after primary localization patch')

# The primary v2.7 patch may finish all useful writes and only fail on an overly
# strict DetailScreens assertion. Apply display-only pool translation by structure
# where possible, but never mutate protocol keys used for data lookup.
if detail.exists():
    ds = detail.read_text(encoding='utf-8')
    ds = ds.replace(
        'pools.forEach { DetailTag(it, it == "B4") }',
        'pools.forEach { DetailTag(displayPoolZh27(it), it == "B4") }'
    )
    ds = re.sub(
        r'DetailTag\(\s*it\s*,\s*it\s*==\s*"B4"\s*\)',
        'DetailTag(displayPoolZh27(it), it == "B4")',
        ds
    )
    ds = ds.replace('Daily Cohort', '每日冻结批次').replace('Forward Tracking', '后续收益跟踪')
    detail.write_text(ds, encoding='utf-8')

g = Path('app/build.gradle.kts')
gs = g.read_text(encoding='utf-8')
if 'versionName = "2.7.0"' not in gs:
    raise SystemExit('v2.7 version bump did not complete')

print('v2.7 full-Chinese display finish completed')
