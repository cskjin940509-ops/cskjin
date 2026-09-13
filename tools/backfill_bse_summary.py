"""Checkpoint official BSE summary rows, without guessing their unit."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
import akshare as ak

p = argparse.ArgumentParser()
p.add_argument('--dates', nargs='+')
p.add_argument('--window', type=int, default=486)
p.add_argument('--batch', type=int, default=10)
a = p.parse_args()
out = Path(__file__).resolve().parents[1] / 'astock_factors/bse_summary_raw'
out.mkdir(parents=True, exist_ok=True)
if not a.dates:
    source = out.parent / 'margin_backfill/sse_range.json'
    dates = sorted({str(r['信用交易日期']) for r in json.loads(source.read_text())['rows']})[-a.window:]
    a.dates = [f'{d[:4]}-{d[4:6]}-{d[6:]}' for d in reversed(dates)]
attempted = 0
for day in a.dates:
    path = out / (day + '.json')
    if path.exists() and json.loads(path.read_text()).get('rows'):
        continue
    if attempted >= a.batch:
        break
    attempted += 1
    try:
        frame = ak.stock_margin_bse(date=day.replace('-', ''))
    except Exception as error:
        print(json.dumps({'date': day, 'error': str(error)[:200]}), flush=True)
        continue
    rows = json.loads(frame.to_json(orient='records', force_ascii=False))
    payload = {'dataDate': day, 'retrievedAt': datetime.now(timezone.utc).isoformat(),
               'source': 'https://www.bse.cn/rzrqjyyexxController/summaryInfoResult.do',
               'positionEligible': False, 'unitStatus': 'REQUIRES_OFFICIAL_METADATA_CHECK', 'rows': rows}
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)
    print(json.dumps({'date': day, 'rows': len(rows)}), flush=True)
