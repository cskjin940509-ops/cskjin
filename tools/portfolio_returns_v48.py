"""Reconstruct 20M paper-book EOD valuations from immutable fills and unadjusted closes.
This is retrospective accounting, never frozen strategy evidence or invented trades.
"""
from datetime import datetime, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import json, math
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]

def number(v):
    return float(v) if isinstance(v, (int, float)) and math.isfinite(v) else None

def book_at(state, ledger, cutoff):
    cash = float((state.get('fundAccounting') or {}).get('inceptionCapital', 1_000_000))
    qty = defaultdict(int)
    for e in state.get('capitalEvents', []):
        if e['timestamp'] <= cutoff: cash += float(e.get('cashContribution', 0))
    for t in sorted(ledger, key=lambda x: (x['timestamp'], x['decisionId'])):
        if t['timestamp'] > cutoff: continue
        sign = 1 if t['side'] == 'BUY' else -1
        qty[t['code']] += sign * int(t['qty'])
        cash -= sign * float(t['amount']) + float(t.get('fee', 0))
    if any(q < 0 for q in qty.values()): raise ValueError('negative replay quantity')
    return round(cash, 2), {c:q for c,q in qty.items() if q}

def build_report(state, ledger, closes, sessions, now):
    event = next((x for x in state.get('capitalEvents', []) if x.get('toCapital') == 20_000_000), None)
    if event is None: return {'rows': [], 'status': 'NO_20M_STAGE'}
    start = event['timestamp'][:10]; today = now.date().isoformat()
    # Prove the immutable fill stream reconstructs the actual current account first.
    cash, qty = book_at(state, ledger, now.isoformat())
    actual = {c:int(p['qty']) for c,p in state.get('positions', {}).items() if p.get('qty')}
    if qty != actual or abs(cash - float(state.get('cash', 0))) > .05:
        raise ValueError('ledger replay does not reconcile to current positions/cash')
    rows = []; previous = None; cumulative = 1.0
    days = [d for d in sorted(set(sessions)) if start <= d <= today and (d < today or now.time() >= time(15, 5))]
    for day in days:
        cutoff = day + 'T23:59:59+08:00'
        c, holdings = book_at(state, ledger, cutoff)
        missing = [code for code in holdings if number(closes.get(code, {}).get(day)) is None or closes[code][day] <= 0]
        assets = None if missing else round(c + sum(q * closes[code][day] for code,q in holdings.items()), 2)
        flow = sum(float(e.get('cashContribution', 0)) for e in state.get('capitalEvents', []) if e['timestamp'][:10] == day)
        pnl = round(assets - previous - flow, 2) if assets is not None and previous is not None else None
        ret = pnl / previous * 100 if pnl is not None and previous > 0 else None
        if day == start: pnl = ret = None
        if ret is not None and cumulative is not None: cumulative *= 1 + ret / 100
        elif day != start: cumulative = None
        rows.append({'date': day, 'closeAssets': assets, 'previousCloseAssets': previous,
                     'netContribution': flow, 'dailyPnl': pnl, 'dailyReturnPct': ret,
                     'cumulativeReturnPct': (cumulative - 1) * 100 if cumulative is not None else None,
                     'status': 'MISSING_CLOSE' if missing else ('STAGE_BASELINE' if day == start else 'RECONSTRUCTED_CLOSE'),
                     'missingCodes': missing, 'holdingCount': len(holdings)})
        previous = assets
    return {'schemaVersion': 1, 'generatedAt': now.isoformat(), 'stageStartedAt': event['timestamp'],
            'capital': 20_000_000, 'status': 'RECONSTRUCTED_ACCOUNTING', 'rows': rows,
            'formulaZh': '本日收益＝本日收盘总资产－前一日收盘总资产－本日净入金；日收益率＝本日收益÷前一日收盘总资产。',
            'baselineNoteZh': '增资发生在9月3日收盘后：当日期初基准含1900万入金，作为2000万阶段起点，不计作投资盈利。',
            'sourceZh': '原始模拟成交账本＋腾讯不复权日K收盘价；事后补算，不冒充当时冻结的收盘证据。',
            'ledgerDecisionCount': len(ledger), 'ledgerReconciled': True}

def raw_closes(code):
    sym = ('sh' if (code.startswith('6') or code == '000300') else 'bj' if code.startswith(('4','8','92')) else 'sz') + code
    url = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?' + urlencode({'param': f'{sym},day,,,320,'})
    with urlopen(Request(url, headers={'User-Agent':'Mozilla/5.0','Referer':'https://gu.qq.com/'}), timeout=10) as r:
        obj = json.load(r)
    data = (obj.get('data') or {}).get(sym) or {}
    # Deliberately never accept qfqday/hfqday for a cash/share accounting valuation.
    return {x[0]: float(x[2]) for x in data.get('day', []) if len(x) >= 5 and float(x[2]) > 0}

def main():
    import run_ai_shadow_portfolio as base
    now = base.now_cn(); folder = ROOT / 'astock_ai_portfolio'
    state = json.loads((folder/'state.json').read_text()); ledger = json.loads((folder/'ledger.json').read_text())
    cache_path = folder/'unadjusted_closes.json'
    cache = base.read_json(cache_path, {})
    # Retrospective data collection runs after core account publication, at most once/day on success.
    ready_day = now.date().isoformat() if now.time() >= time(15,5) else 'intraday-' + now.date().isoformat()
    codes = sorted({t['code'] for t in ledger} | {'000300'})
    todo = [c for c in codes if (cache.get(c) or {}).get('fetchedDay') != ready_day]
    def fetch(c):
        try: return c, raw_closes(c), None
        except Exception as e: return c, {}, type(e).__name__
    with ThreadPoolExecutor(max_workers=6) as pool:
        for c, rows, error in pool.map(fetch, todo):
            if rows: cache[c] = {'fetchedDay': ready_day, 'fetchedAt': now.isoformat(), 'closes': rows, 'adjustment':'NONE'}
            elif error: print('close fetch unavailable', c, error)
    closes = {c:x.get('closes', {}) for c,x in cache.items()}
    sessions = sorted(closes.get('000300', {}))
    if not sessions: raise ValueError('missing index calendar; cannot assume weekdays are exchange sessions')
    report = build_report(state, ledger, closes, sessions, now)
    base.write_json(cache_path, cache); base.write_json(folder/'daily_returns.json', report)
    print(json.dumps({'rows':report['rows'], 'ledgerReconciled':report['ledgerReconciled']}, ensure_ascii=False))

if __name__ == '__main__': main()
