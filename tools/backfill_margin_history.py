"""Resumable exchange-total history collection; never fills missing days with zero."""
import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
import akshare as ak
from collect_slow_money_factors_v2 import fetch_market_margin_summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--end', required=True)
    parser.add_argument('--days', type=int, default=486)
    parser.add_argument('--batch', type=int, default=5)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    calendar = ak.tool_trade_date_hist_sina()
    days = sorted({str(d)[:10] for d in calendar['trade_date'] if str(d)[:10] <= args.end})[-args.days:]
    args.output.mkdir(parents=True, exist_ok=True)
    # Reuse already collected, complete exchange totals before making requests.
    source_root = Path(__file__).resolve().parents[1] / 'astock_factors'
    for source in [source_root / 'latest.json', *sorted((source_root / 'history').glob('*.json'))]:
        record = json.loads(source.read_text(encoding='utf-8'))
        summary = (record.get('margin') or {}).get('marketSummary') or {}
        if not summary.get('complete') or set(summary.get('exchangeBalances', {})) != {'SSE', 'SZSE', 'BSE'}:
            continue
        day = summary.get('dataDate')
        if day not in days:
            continue
        path = args.output / (day + '.json')
        if path.exists() and json.loads(path.read_text()).get('complete'):
            continue
        row = dict(summary, importedFrom=str(source.relative_to(source_root)),
                   historicalAvailableAt=None, importedAt=datetime.now(timezone.utc).isoformat())
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(path)
    attempted = 0
    for day in reversed(days):
        path = args.output / (day + '.json')
        if path.exists() and json.loads(path.read_text()).get('complete'):
            continue
        if attempted >= args.batch:
            break
        row = fetch_market_margin_summary(date.fromisoformat(day))
        row['retrievedAt'] = datetime.now(timezone.utc).isoformat()
        row['historicalAvailableAt'] = None
        row['note'] = '历史回补；抓取时间不等于历史发布时间，不可用于无前视偏差回测'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(path)
        attempted += 1
        print(json.dumps({'day': day, 'complete': row['complete'], 'errors': row['errors']}), flush=True)
    complete = [day for day in days if (args.output / (day + '.json')).exists()
                and json.loads((args.output / (day + '.json')).read_text()).get('complete')]
    print(json.dumps({'requested': len(days), 'complete': len(complete),
                      'missing': [d for d in days if d not in complete]}), flush=True)


if __name__ == '__main__':
    main()
