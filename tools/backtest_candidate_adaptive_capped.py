#!/usr/bin/env python3
import json
from collections import defaultdict, Counter
import backtest_candidate_8day as base
import backtest_candidate_8day_fast as fast

OUT = base.ROOT / 'backtests' / 'candidate_adaptive_capped_backtest_20261007.json'
MAX_WEIGHT = 0.15
SETUP_MULT = {'趋势回踩': 1.10, '突破回踩': 1.00, '临界突破': 0.70}


def max_hold_days(setup, score):
    score = float(score or 0)
    if setup == '趋势回踩':
        return 8 if score >= 85 else 6
    if setup == '突破回踩':
        return 6 if score >= 85 else 5
    if setup == '临界突破':
        return 4 if score >= 85 else 3
    return 5


def post_entry_closes(prices, code, buy_index, end_index):
    vals = []
    pdata = prices.get(code) or {}
    for d in base.TRADING_DAYS[buy_index:end_index + 1]:
        v = (pdata.get(d) or {}).get('close')
        if v is not None:
            vals.append(float(v))
    return vals


def exit_decision(pos, prices, i):
    # Decision at today's open uses only closes through yesterday.
    age = i - pos['buy_index']
    if age <= 0:
        return False, 'same_day'
    hist = post_entry_closes(prices, pos['code'], pos['buy_index'], i - 1)
    if not hist:
        return False, 'no_post_entry_close'
    prev = hist[-1]
    entry = pos['entry_price']

    # Hard risk failure, executed next session open5 VWAP.
    if prev <= entry * 0.95:
        return True, 'hard_stop_prior_close_5pct'

    # Early thesis failure after at least two completed holding sessions.
    if age >= 2 and len(hist) >= 2:
        prior = hist[-2]
        if prev < entry * 0.99 and prev <= prior:
            return True, 'early_setup_failure'

    # Three sessions is the default holding horizon.
    if age < 3:
        return False, 'base_3day_hold'

    # At/after day 3, extension is earned only by demonstrated profit + momentum.
    sma3 = sum(hist[-3:]) / min(3, len(hist))
    mom2 = (hist[-1] / hist[-3] - 1) if len(hist) >= 3 and hist[-3] > 0 else 0.0
    strong = prev >= entry * 1.02 and prev >= sma3 and mom2 > 0
    max_hold = pos['max_hold']
    if strong and age < max_hold:
        return False, 'profit_trend_extension'
    return True, 'day3_or_trend_exit'


def candidate_quality(x):
    s = max(float(x.get('score') or 0) - 70.0, 1.0)
    return (s * s) * SETUP_MULT.get(x.get('setup'), 0.90)


def waterfill_alloc(candidates, cash, nav, mode):
    if not candidates or cash <= 1e-12 or nav <= 1e-12:
        return {}
    cap = MAX_WEIGHT * nav
    if mode == 'equal':
        raw = {x['code']: 1.0 for x in candidates}
    else:
        raw = {x['code']: candidate_quality(x) for x in candidates}

    remaining = cash
    active = set(raw)
    alloc = {c: 0.0 for c in raw}
    # Iterative capped proportional allocation; leftover cash is allowed.
    while active and remaining > 1e-12:
        den = sum(raw[c] for c in active)
        if den <= 0:
            break
        proposed = {c: remaining * raw[c] / den for c in active}
        capped_any = False
        for c in list(active):
            room = cap - alloc[c]
            if room <= 1e-12:
                active.remove(c)
                continue
            if proposed[c] >= room - 1e-12:
                alloc[c] += room
                remaining -= room
                active.remove(c)
                capped_any = True
        if not capped_any:
            for c in active:
                alloc[c] += proposed[c]
            remaining = 0.0
            break
    return {c: v for c, v in alloc.items() if v > 1e-12}


def simulate(cands, prices, mode):
    byday = defaultdict(list)
    for x in cands:
        byday[x['date']].append(x)

    cash = 1.0
    positions = {}
    daily = []
    trades = []
    pending = []
    total_buy_value = 0.0
    total_sell_value = 0.0
    exposure_sum = 0.0
    position_count_sum = 0
    max_single_weight_seen = 0.0

    for i, d in enumerate(base.TRADING_DAYS):
        # Mark current NAV at today's executable open price.
        nav_open = cash
        open_px = {}
        for code, p in positions.items():
            px = (prices.get(code) or {}).get(d, {}).get('open5_vwap')
            if px is None:
                px = p.get('last_close', p['entry_price'])
            open_px[code] = px
            nav_open += p['shares'] * px

        # 1) Exit only positions whose thesis failed / horizon ended. No rebalance of survivors.
        survivors = {}
        for code, p in positions.items():
            should_exit, reason = exit_decision(p, prices, i)
            px = open_px[code]
            if should_exit:
                proceeds = p['shares'] * px
                cash += proceeds
                total_sell_value += proceeds
                trades.append({
                    'code': code, 'name': p['name'], 'setup': p['setup'], 'score': p['score'],
                    'signal_date': p['signal_date'], 'buy_date': p['buy_date'], 'exit_date': d,
                    'entry_price': p['entry_price'], 'exit_price': px,
                    'holding_sessions': i - p['buy_index'], 'exit_reason': reason,
                    'return': px / p['entry_price'] - 1, 'allocation': p['initial_allocation']
                })
            else:
                survivors[code] = p
        positions = survivors

        # Recompute NAV after exits; exits at the same open VWAP do not change NAV except stale-price edge cases.
        nav_after_exit = cash
        for code, p in positions.items():
            px = (prices.get(code) or {}).get(d, {}).get('open5_vwap')
            if px is None:
                px = p.get('last_close', p['entry_price'])
            nav_after_exit += p['shares'] * px

        # 2) Buy prior-day signals using ONLY available cash. Existing holdings are untouched.
        signal_date = base.TRADING_DAYS[i - 1] if i > 0 else None
        raw_new = byday.get(signal_date, []) if signal_date else []
        new_candidates = []
        for x in raw_new:
            code = x['code']
            if code in positions:
                continue  # repeated signals do not add or reset the clock while already held
            px = (prices.get(code) or {}).get(d, {}).get('open5_vwap')
            if px and px > 0:
                new_candidates.append(x)

        allocs = waterfill_alloc(new_candidates, cash, nav_after_exit, mode)
        for x in new_candidates:
            code = x['code']
            alloc = allocs.get(code, 0.0)
            if alloc <= 1e-12:
                continue
            px = (prices.get(code) or {}).get(d, {}).get('open5_vwap')
            if not px:
                continue
            alloc = min(alloc, cash)
            cash -= alloc
            total_buy_value += alloc
            positions[code] = {
                **x,
                'signal_date': x['date'],
                'buy_date': d,
                'buy_index': i,
                'entry_price': px,
                'shares': alloc / px,
                'initial_allocation': alloc,
                'max_hold': max_hold_days(x.get('setup', ''), x.get('score', 0)),
                'last_close': px,
            }

        # 3) End-of-day mark. No resizing of existing positions.
        nav_close = cash
        invested = 0.0
        max_w = 0.0
        for code, p in positions.items():
            close = (prices.get(code) or {}).get(d, {}).get('close')
            if close is None:
                close = p.get('last_close', p['entry_price'])
            p['last_close'] = close
            value = p['shares'] * close
            invested += value
            nav_close += value
        for code, p in positions.items():
            value = p['shares'] * p['last_close']
            max_w = max(max_w, value / max(nav_close, 1e-12))
        max_single_weight_seen = max(max_single_weight_seen, max_w)
        exposure = invested / max(nav_close, 1e-12)
        exposure_sum += exposure
        position_count_sum += len(positions)
        daily.append({
            'date': d, 'nav': nav_close, 'invested': invested, 'cash': cash,
            'exposure': exposure, 'positions': len(positions), 'max_position_weight': max_w
        })

    for x in byday.get(base.TRADING_DAYS[-1], []):
        pending.append({**x, 'signal_date': x['date'], 'status': 'pending_next_session'})

    peak = 1.0
    prev = 1.0
    maxdd = 0.0
    for r in daily:
        r['daily_return'] = r['nav'] / prev - 1
        prev = r['nav']
        peak = max(peak, r['nav'])
        r['drawdown'] = r['nav'] / peak - 1
        maxdd = min(maxdd, r['drawdown'])

    wins = sum(1 for t in trades if t['return'] > 0)
    reason_counts = Counter(t['exit_reason'] for t in trades)
    hold_counts = Counter(t['holding_sessions'] for t in trades)
    open_positions = []
    for code, p in positions.items():
        mark = p.get('last_close', p['entry_price'])
        open_positions.append({
            'code': code, 'name': p['name'], 'setup': p['setup'], 'score': p['score'],
            'signal_date': p['signal_date'], 'buy_date': p['buy_date'], 'entry_price': p['entry_price'],
            'last_mark_price': mark, 'unrealized_return': mark / p['entry_price'] - 1,
            'max_hold': p['max_hold']
        })

    return {
        'summary': {
            'end_nav': daily[-1]['nav'],
            'cumulative_return': daily[-1]['nav'] - 1,
            'max_drawdown': maxdd,
            'realized_trades': len(trades),
            'realized_win_rate': wins / len(trades) if trades else None,
            'open_positions': len(positions),
            'pending_entries': len(pending),
            'avg_exposure': exposure_sum / len(daily),
            'avg_positions': position_count_sum / len(daily),
            'max_single_weight_seen': max_single_weight_seen,
            'gross_buy_turnover_per_initial_nav': total_buy_value,
            'gross_sell_turnover_per_initial_nav': total_sell_value,
            'exit_reason_counts': dict(reason_counts),
            'holding_session_counts': {str(k): v for k, v in sorted(hold_counts.items())},
        },
        'daily': daily,
        'trades': trades,
        'open_positions': open_positions,
        'pending': pending,
    }


def main():
    cands, missing = base.candidate_rows()
    codes = {x['code'] for x in cands}
    prices, errs, server = fast.load_prices(codes)
    coverage = []
    for x in cands:
        bd = base.next_session(x['date'])
        if bd and not (prices.get(x['code']) or {}).get(bd, {}).get('open5_vwap'):
            coverage.append({'signal_date': x['date'], 'buy_date': bd, 'code': x['code'], 'name': x['name']})
    fallbacks = [
        {'date': d, 'code': c, 'method': p.get('method')}
        for c, ds in prices.items() for d, p in ds.items()
        if p.get('method') != 'tdx_amount_volume'
    ]
    res = {
        'as_of': '2026-10-07',
        'latest_market_date': '2026-09-30',
        'methodology': {
            'signal': 'candidate list generated near/after signal-day close',
            'execution': 'all buys and exits use next-session first 5-minute VWAP',
            'portfolio': 'existing positions are never resized; exits create cash; new signals use only available cash',
            'single_name_cap': MAX_WEIGHT,
            'base_holding': '3 trading sessions',
            'extension': 'after day 3, extend only when prior close >= entry*1.02, >= 3-close average and 2-session momentum > 0',
            'max_holding': 'trend pullback: 8d if score>=85 else 6d; breakout pullback: 6d if score>=85 else 5d; critical breakout: 4d if score>=85 else 3d',
            'hard_exit': 'prior close <= entry*0.95; executed next session open5 VWAP',
            'early_exit': 'after >=2 sessions, prior close < entry*0.99 and <= previous close; executed next session open5 VWAP',
            'repeated_signal': 'ignored while same stock is already held',
            'equal_variant': 'available cash allocated equally among new candidates, capped at 15% of current NAV each',
            'factor_variant': 'available cash allocated by (score-70)^2 * setup multiplier, capped at 15% of current NAV each',
            'cash': 'left idle whenever candidate capacity is insufficient; no forced full investment',
            'fees': '0',
        },
        'candidate_count': len(cands),
        'unique_codes': len(codes),
        'missing_history_days': missing,
        'price_errors': errs,
        'coverage_issues': coverage,
        'vwap_fallbacks': fallbacks,
        'tdx_server': f'{server[0]}:{server[1]}',
        'adaptive_equal': simulate(cands, prices, 'equal'),
        'adaptive_factor': simulate(cands, prices, 'factor'),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({
        'output': str(OUT.relative_to(base.ROOT)),
        'server': res['tdx_server'],
        'candidates': len(cands),
        'codes': len(codes),
        'price_errors': len(errs),
        'coverage': len(coverage),
        'fallbacks': len(fallbacks),
        'adaptive_equal': res['adaptive_equal']['summary'],
        'adaptive_factor': res['adaptive_factor']['summary'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
