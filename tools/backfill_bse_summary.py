"""Checkpoint official BSE summary rows, without guessing their unit."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
import akshare as ak

p = argparse.ArgumentParser()
p.add_argument('--dates', nargs='+', required=True)
a = p.parse_args()
out = Path(__file__).resolve().parents[1] / 'astock_factors/bse_summary_raw'
out.mkdir(parents=True, exist_ok=True)
for day in a.dates:
    frame = ak.stock_margin_bse(date=day.replace('-', ''))
    rows = json.loads(frame.to_json(orient='records', force_ascii=False))
    payload = {'dataDate': day, 'retrievedAt': datetime.now(timezone.utc).isoformat(),
               'source': 'https://www.bse.cn/rzrqjyyexxController/summaryInfoResult.do',
               'positionEligible': False, 'unitStatus': 'REQUIRES_OFFICIAL_METADATA_CHECK', 'rows': rows}
    path = out / (day + '.json')
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'date': day, 'rows': len(rows)}), flush=True)
