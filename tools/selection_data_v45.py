"""Collect only data available at the decision time, including held names off radar."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from selection_rules_v45 import finite, indicators


def get_json(url):
    request = Request(url, headers={'User-Agent': 'Mozilla/5.0 AStockSelection/4.5', 'Referer': 'https://quote.eastmoney.com/'})
    with urlopen(request, timeout=6) as response:
        return json.loads(response.read(12 * 1024 * 1024))


def daily_bars(code, exchange=None):
    sh = exchange == 'sh' or code.startswith(('6', 'BK'))
    params = {'secid': ('1.' if sh else '0.') + code, 'klt': 101,
              'fqt': 1, 'lmt': 65, 'end': '20500101',
              'fields1': 'f1,f2,f3,f4,f5,f6', 'fields2': 'f51,f52,f53,f54,f55,f56,f57'}
    try:
        raw = (get_json('https://push2his.eastmoney.com/api/qt/stock/kline/get?' + urlencode(params)).get('data') or {}).get('klines') or []
        rows = []
        for x in raw:
            a = x.split(',')
            if len(a) >= 7:
                rows.append(dict(date=a[0], **{k: finite(a[i]) for k, i in [('open', 1), ('close', 2), ('high', 3), ('low', 4), ('amount', 6)]}))
        if len(rows) >= 21:
            return rows
    except Exception:
        pass
    # Tencent fallback has no verified traded amount: ATR works, buy gates remain closed.
    sym = ('sh' if sh else 'sz') + code
    obj = get_json('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?' + urlencode({'param': f'{sym},day,,,65,qfq'}))
    data = (obj.get('data') or {}).get(sym) or {}
    return [{'date': a[0], 'open': finite(a[1]), 'close': finite(a[2]), 'high': finite(a[3]),
             'low': finite(a[4]), 'amount': None} for a in (data.get('qfqday') or data.get('day') or []) if len(a) >= 5]


def sector_members(board):
    rows = []
    total = None
    for page in range(1, 16):
        q = {'pn': page, 'pz': 100, 'po': 1, 'np': 1, 'fltt': 2, 'invt': 2, 'fid': 'f12',
             'fs': 'b:' + board, 'fields': 'f2,f3,f6,f12,f14,f62,f184'}
        payload = get_json('https://push2.eastmoney.com/api/qt/clist/get?' + urlencode(q)).get('data') or {}
        total = int(payload.get('total') or 0)
        part = payload.get('diff') or []
        if isinstance(part, dict):
            part = list(part.values())
        rows.extend(part)
        if len(rows) >= total or not part:
            break
    unique = {str(x.get('f12')): x for x in rows if x.get('f12')}
    if not total or len(unique) != total:
        return {'complete': False, 'total': total, 'observed': len(unique), 'ranks': {}, 'rows': {}}
    # Cross-sectional definition is public and fixed; missing observations invalidate rank.
    valid = [x for x in unique.values() if all(finite(x.get(k)) is not None for k in ('f2', 'f3', 'f6', 'f184'))]
    scored = sorted(valid, key=lambda x: (.6 * min(100, max(0, 50 + finite(x['f184']) * 2))
                         + .4 * min(100, max(0, 50 + finite(x['f3']) * 5))), reverse=True)
    ranks = {str(x['f12']): (i + 1) / len(scored) for i, x in enumerate(scored)}
    return {'complete': len(valid) >= max(1, total * .95), 'total': total, 'observed': len(valid), 'ranks': ranks,
            'rows': {str(x['f12']): {'price': finite(x['f2']), 'changePct': finite(x['f3']),
                                   'amount': finite(x['f6']), 'mainFlowPct': finite(x['f184'])} for x in valid}}


def enrich(state, radar, quotes, now):
    today = now.date().isoformat()
    data = state.setdefault('selectionData45', {})
    histories = data.setdefault('histories', {})
    if os.getenv('ASTOCK_DISABLE_QUOTE_FETCH') != '1':
        codes = set(state.get('positions') or {}) | set(radar.get('stocks') or {})
        needed = [c for c in codes if (histories.get(c) or {}).get('collectedDate') != today]
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {pool.submit(daily_bars, c): c for c in needed}
            for f in as_completed(futures):
                c = futures[f]
                try:
                    rows = f.result()
                    histories[c] = {'collectedDate': today, 'availableAt': now.isoformat(),
                                    'bars': [x for x in rows if x.get('date', '') < today]}
                except Exception as exc:
                    histories[c] = {'collectedDate': today, 'bars': [], 'error': type(exc).__name__}
        # Full sector universe, not the top-15 radar list. Same-day, one cycle only.
        sectors = {x['name']: x for x in radar.get('mainlines') or [] if x.get('boardCode') and x.get('name')}
        board_cache = data.setdefault('sectorBoards', {})
        board_cache.update({name: x['boardCode'] for name, x in sectors.items()})
        for pos in (state.get('positions') or {}).values():
            name = pos.get('sector')
            if name in board_cache and name not in sectors:
                sectors[name] = {'name': name, 'boardCode': board_cache[name], 'stage': 'HOLDING_TRACK_ONLY'}
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {pool.submit(sector_members, x['boardCode']): name for name, x in sectors.items()}
            ranks = {}
            for f in as_completed(futures):
                try:
                    ranks[futures[f]] = dict(f.result(), availableAt=now.isoformat())
                except Exception as exc:
                    ranks[futures[f]] = {'complete': False, 'error': type(exc).__name__}
            data['sectorRanks'] = ranks
        # Index trading dates prevent weekends, holidays or missed jobs becoming confirmations.
        try:
            calendar = daily_bars('000300', exchange='sh')
            data['marketSessions'] = sorted({x['date'] for x in calendar if x['date'] <= today})
        except Exception:
            data.setdefault('marketSessions', [])
        sector_history = data.setdefault('sectorHistory', {})
        needed_boards = {name: x['boardCode'] for name, x in sectors.items()
                         if (sector_history.get(name) or {}).get('collectedDate') != today}
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {pool.submit(daily_bars, board): name for name, board in needed_boards.items()}
            for f in as_completed(futures):
                try:
                    rows = sorted((x for x in f.result() if x['date'] < today), key=lambda x: x['date'])
                    r5 = (rows[-1]['close'] / rows[-6]['close'] - 1) * 100 if len(rows) >= 6 else None
                    sector_history[futures[f]] = {'collectedDate': today, 'return5Pct': r5}
                except Exception:
                    sector_history[futures[f]] = {'collectedDate': today, 'return5Pct': None}
        for name, sector in sectors.items():
            sector['return5Pct'] = (sector_history.get(name) or {}).get('return5Pct')
            if sector['stage'] == 'HOLDING_TRACK_ONLY':
                members = list((ranks.get(name) or {}).get('rows', {}).values())
                if (ranks.get(name) or {}).get('complete') and members:
                    total_amount = sum(x['amount'] for x in members)
                    breadth = sum(x['changePct'] > 0 for x in members) / len(members) * 100
                    flow = sum(x['mainFlowPct'] * x['amount'] for x in members) / total_amount if total_amount > 0 else None
                    sector.update(breadthPct=breadth, mainFlowPct=flow,
                                  changePct=sum(x['changePct'] for x in members) / len(members))
                    if breadth < 40 and flow is not None and flow < 0:
                        sector['stage'] = 'DECLINING'
                radar.setdefault('mainlines', []).append(sector)
    technical = {}
    for code, q in quotes.items():
        technical[code] = indicators((histories.get(code) or {}).get('bars', []), now, q.get('prevClose'))
    data['technical'] = technical
    data['collectedAt'] = now.isoformat()
    return data
