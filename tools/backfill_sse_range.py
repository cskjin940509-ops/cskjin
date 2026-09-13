"""Collect SSE margin history in one range request, retaining raw dated rows."""
import json
from datetime import datetime, timezone
from pathlib import Path
import akshare as ak

def main():
    frame = ak.stock_margin_sse(start_date='20240901', end_date='20260911')
    rows = json.loads(frame.to_json(orient='records', force_ascii=False))
    dates = [str(r['信用交易日期']) for r in rows]
    if len(dates) != len(set(dates)):
        raise ValueError('duplicate trading dates')
    out = Path(__file__).resolve().parents[1] / 'astock_factors/margin_backfill/sse_range.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {'exchange': 'SSE', 'source': 'https://www.sse.com.cn/market/othersdata/margin/sum/',
               'retrievedAt': datetime.now(timezone.utc).isoformat(),
               'historicalAvailableAt': None, 'rows': rows}
    tmp = out.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(out)
    print(json.dumps({'rows': len(rows), 'first': min(dates) if dates else None,
                      'last': max(dates) if dates else None, 'path': str(out)}))

if __name__ == '__main__':
    main()
