"""Point-in-time research rules. No broker, network, or accounting mutations."""
from __future__ import annotations

from datetime import datetime, time
from statistics import mean
from zoneinfo import ZoneInfo
from shadow_fund_v3 import finite

VERSION = 'v4.5-selection-pool-core-t'
CN = ZoneInfo('Asia/Shanghai')
PARAMETERS = {
    'singleLimit': .08, 'leaderLimit': .10, 'sectorLimit': .25,
    'correlationLimit': .35, 'normalTurnoverLimit': .20,
    'minCompleteHoldingDays': 2, 'targetConfirmations': 3,
    'atrStopMultiple': 1.5, 'trailingAtrMultiple': 2.,
    'stopMin': .04, 'stopMax': .08, 'trailingActivation': .08,
    'tBaseFraction': .20, 'tNavLimit': .01, 'tMaxPairsPerDay': 1,
    'tMinNetEdge': .003, 'tMaxQuoteGapSeconds': 600,
    'parameterStatus': 'INITIAL_RESEARCH_NOT_OUT_OF_SAMPLE_VALIDATED',
}
RULES_ZH = {
    'newEntry': '大盘许可→潜在/确认板块至少两类独立证据（含资金）→板块完整样本前20%→回撤企稳/突破回踩；双源偏差≤0.3%，资金滞后时点、ADV20及成本检查通过才分批买入。',
    'position': '潜在主线初始2.5%，确认主线4%；普通单股≤8%，两次确认龙头≤10%，板块≤25%，相关板块≤35%；最多加仓两次，不因单纯下跌补仓。',
    'rebalance': '10:00–10:30、14:30–14:50普通成交；目标连续3个不同快照确认；调仓差额不足3个百分点不交易（首次小仓和已确认未成交余量除外）；普通双边换手≤20%。',
    'exit': '掉出候选只停加仓。至少2个完整交易日观察；1日失效观察，2日减半，3日退出；板块2日确认衰退退出。硬止损及组合风险优先，待退出数量不因T+1/跌停/部分成交丢失。',
    'stop': '1.5×ATR14/价格，距离限制4%–8%；ATR缺失保守4%并标注降级。盈利8%启动2×ATR移动保护，风险线只收紧不放宽。',
    'risk': '当日单位净值-1.5%停买，-2.5%总仓位目标降低25%；已确认日终净值回撤-5%仓位上限减半，-8%暂停新仓至少5个真实交易日并等待复核。',
    't': '仅模拟先卖后买；每股每日最多1组，≤昨日底仓20%且≤净值1%。仅震荡且冲高转弱时卖，回落企稳才买回。强趋势、退出风险、缺行情、价差不足覆盖双边成本时不做T。未买回/部分买回也计入机会损益。',
    'lowPoint': '判断相对买入区间，不宣称预测最低点：价格回撤接近20日均线/突破位，同时连续快照不再创新低并回升，且板块与资金未失效。',
    'audit': '新规则只影响生效后的模拟成交；旧100万阶段、2000万容量、完整账本保留。T收益单列，不二次计入净值、不改写会计平均成本。所有参数待样本外验证。',
}


def stamp(value, day=None):
    try:
        s = str(value or '').strip()
        if s.isdigit() and len(s) == 13:
            return datetime.fromtimestamp(int(s) / 1000, CN)
        if s.isdigit() and len(s) == 14:
            return datetime.strptime(s, '%Y%m%d%H%M%S').replace(tzinfo=CN)
        if day and len(s) in (6, 8) and 'T' not in s:
            s = day + 'T' + (f'{s[:2]}:{s[2:4]}:{s[4:]}' if len(s) == 6 else s)
        d = datetime.fromisoformat(s.replace('Z', '+00:00'))
        return d.replace(tzinfo=CN) if d.tzinfo is None else d.astimezone(CN)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def fresh(value, now, seconds=180):
    d = stamp(value, now.date().isoformat())
    return d is not None and 0 <= (now - d).total_seconds() <= seconds


def normal_window(now):
    return time(10) <= now.time() <= time(10, 30) or time(14, 30) <= now.time() <= time(14, 50)


def indicators(bars, now, prev_close=None):
    # Explicitly drop today's unfinished bar, future bars and duplicate dates.
    by_day = {x['date']: x for x in bars if x.get('date', '') < now.date().isoformat()
              and all(finite(x.get(k), 0) > 0 for k in ('high', 'low', 'close'))}
    rows = [by_day[d] for d in sorted(by_day)][-65:]
    if len(rows) < 21:
        return {'ready': False, 'reasonZh': '已完成日线不足21根', 'sampleDays': len(rows)}
    last = rows[-1]
    # Refuse incompatible raw/adjusted price bases (e.g. ex-rights day).
    if prev_close and abs(last['close'] / prev_close - 1) > .003:
        return {'ready': False, 'reasonZh': '日线与昨收价格基准不一致，等待除权/复权校验'}
    tr = [max(x['high'] - x['low'], abs(x['high'] - p['close']), abs(x['low'] - p['close']))
          for p, x in zip(rows[:-1], rows[1:])]
    amounts = [finite(x.get('amount')) for x in rows[-20:]]
    valid_amount = all(x is not None and x > 0 for x in amounts)
    hi, lo = max(x['high'] for x in rows[-20:]), min(x['low'] for x in rows[-20:])
    ma20 = mean(x['close'] for x in rows[-20:])
    return {'ready': True, 'dataDate': last['date'], 'sampleDays': len(rows),
            'atr14': mean(tr[-14:]), 'ma20': ma20, 'high20': hi, 'low20': lo,
            'previousHigh20': max(x['high'] for x in rows[-21:-1]),
            'return5Pct': (last['close'] / rows[-6]['close'] - 1) * 100,
            'slope20Pct': (ma20 / mean(x['close'] for x in rows[-25:-5]) - 1) * 100 if len(rows) >= 25 else None,
            'adv20': mean(amounts) if valid_amount else None,
            'volumeRatio5to20': mean(amounts[-5:]) / mean(amounts) if valid_amount else None}


def market_regime(snapshot, now, macro=None):
    result = {'state': 'UNKNOWN', 'cap': 0., 'allowNew': False, 'reasonZh': '缺少当日大盘广度证据', 'missingEvidence': []}
    if not snapshot or snapshot.get('sourceDate') != now.date().isoformat() or not snapshot.get('verifiedToday'):
        return result
    if not fresh(snapshot.get('availableAt'), now, 900):
        result['reasonZh'] = '大盘快照过期/时间在未来'; return result
    values = [finite((snapshot.get('indices') or {}).get(k, {}).get('changePct'))
              for k in ('sh000001', 'sh000300', 'sz399006')]
    up, down = finite(snapshot.get('up')), finite(snapshot.get('down'))
    if any(x is None for x in values):
        return result
    # Broad index crash still controls risk even if breadth is missing.
    avg = mean(values)
    if avg <= -2 or min(values) <= -3:
        return dict(result, state='RISK', cap=.10, reasonZh='核心指数急跌，风险退出优先')
    if up is None or down is None or up + down < 2000:
        result['reasonZh'] = '全市场广度缺失/样本不足2000，禁止用候选样本冒充全市场'; return result
    breadth = up / (up + down)
    if breadth < .25:
        state, cap = 'RISK', .10
    elif breadth < .4 or avg < -.8:
        state, cap = 'DEFENSIVE', .25
    elif breadth >= .75 and avg >= 1.5:
        state, cap = 'STRONG', 1.
    elif breadth >= .6 and avg >= .5:
        state, cap = 'POSITIVE', .8
    else:
        state, cap = 'NEUTRAL', .6
    # Macro inputs are evidence flags supplied as-of, never invented numeric weights.
    macro = macro or {}
    missing = [k for k in ('margin', 'broadEtf', 'usRisk', 'us30y', 'cn10y')
               if not isinstance(macro.get(k), dict) or not macro[k].get('verified')
               or not fresh(macro[k].get('availableAt'), now, 4 * 86400)]
    if missing:
        cap = min(cap, .30)
    if any(x.get('riskOff') is True for k, x in macro.items() if isinstance(x, dict) and k not in missing):
        cap = min(cap, .25)
    return {'state': state, 'cap': cap, 'allowNew': state != 'RISK',
            'breadthPct': round(breadth * 100, 2), 'missingEvidence': missing,
            'reasonZh': f'市场广度{breadth:.1%}；宏观证据缺失时上限收紧至30%' if missing else '大盘量价广度与时点通过'}


def sector_evidence(stock, sector, today, now=None):
    evidence = []
    if (finite(sector.get('breadthPct'), 0) >= 55 and finite(sector.get('changePct'), -100) > -1):
        evidence.append('B0')
    if finite(sector.get('mainFlowPct'), 0) > 0:
        evidence.append('B3')
    margin = stock.get('marginData') or {}
    margin_day = str(margin.get('dataDate') or '')
    if stamp(margin_day) and margin_day < today and finite(margin.get('balanceChange1d'), 0) > 0:
        # A bounded lag rejects old data; availableAt, when supplied, is also checked.
        lag = (datetime.fromisoformat(today) - datetime.fromisoformat(margin_day)).days
        if lag <= 7 and (not margin.get('availableAt') or (now and stamp(margin['availableAt']) and stamp(margin['availableAt']) <= now)):
            evidence.append('B1')
    etf = stock.get('etfData') or {}
    etf_day = str(etf.get('dataDate') or '')
    if stamp(etf_day) and etf_day < today and finite(etf.get('netFlow'), 0) > 0:
        if (datetime.fromisoformat(today) - datetime.fromisoformat(etf_day)).days <= 7:
            evidence.append('B2')
    return evidence


def price_setup(price, technical, samples):
    if not technical.get('ready') or len(samples) < 3:
        return {'ready': False, 'kind': 'WAIT', 'reasonZh': '等待完整日线与至少3个有效盘中快照'}
    ma, atr, hi, lo = (technical[k] for k in ('ma20', 'atr14', 'high20', 'low20'))
    a, b, c = samples[-3:]
    gap1 = (stamp(b['at']) - stamp(a['at'])).total_seconds()
    gap2 = (stamp(c['at']) - stamp(b['at'])).total_seconds()
    if not (180 <= gap1 <= 600 and 180 <= gap2 <= 600):
        return {'ready': False, 'kind': 'WAIT', 'reasonZh': '盘中样本间隔不足或断档，等待连续确认'}
    stabilized = b['price'] >= a['price'] * .999 and c['price'] > b['price'] * 1.001
    near_support = ma - .6 * atr <= price <= ma + .5 * atr
    breakout = technical['previousHigh20']
    retest = a['price'] >= breakout and breakout - .3 * atr <= b['price'] <= breakout + .3 * atr
    position = (price - lo) / (hi - lo) if hi > lo else 1.
    if stabilized and near_support and position <= .8:
        kind, reason = 'PULLBACK_RECOVERY', '均线附近回撤企稳，连续快照止跌回升'
    elif stabilized and retest and price <= breakout + .5 * atr:
        kind, reason = 'BREAKOUT_RETEST', '突破位回踩确认，未明显偏离支撑'
    else:
        return {'ready': False, 'kind': 'WAIT', 'reasonZh': '未确认回撤企稳/突破回踩，继续等待', 'position20': position}
    stop_distance = min(.08, max(.04, 1.5 * atr / price))
    reward = max(0., hi - price)
    return {'ready': True, 'kind': kind, 'reasonZh': reason, 'position20': position,
            'support': ma if kind == 'PULLBACK_RECOVERY' else breakout,
            'riskDistancePct': stop_distance * 100, 'potentialRewardPct': reward / price * 100}


def stop_lines(pos, price, technical):
    basis = finite(pos.get('riskBasis'), finite(pos.get('avgCost'), price))
    atr = finite(technical.get('atr14')) if technical.get('ready') else None
    distance = min(.08, max(.04, 1.5 * atr / price)) if atr else .04
    hard = max(finite(pos.get('hardStopPrice'), 0), basis * (1 - distance))
    peak = max(finite(pos.get('peakPrice'), basis), price)
    trailing = finite(pos.get('trailingStopPrice'), 0)
    if peak >= basis * 1.08:
        trail_distance = min(.08, max(.04, 2 * atr / price)) if atr else .04
        trailing = max(trailing, peak * (1 - trail_distance))
    return {'riskBasis': basis, 'hardStopPrice': round(hard, 4), 'peakPrice': peak,
            'trailingStopPrice': round(trailing, 4), 'atrFallback': atr is None,
            'atr14': atr, 'stopDistancePct': distance * 100}


def t_signal(price, tech, samples, net_cost_pct):
    result = {'eligible': False, 'reasonZh': '等待震荡、冲高转弱和足够净价差'}
    if not tech.get('ready') or len(samples) < 3 or tech.get('slope20Pct') is None:
        return dict(result, reasonZh='日线/连续盘中数据不足，暂停做T')
    a, b, c = samples[-3:]
    gaps = [(stamp(y['at']) - stamp(x['at'])).total_seconds() for x, y in ((a, b), (b, c))]
    if not all(180 <= x <= 600 for x in gaps):
        return dict(result, reasonZh='行情采样间隔不满足3–10分钟，暂停做T')
    if abs(tech['slope20Pct']) > 1.5 or abs(tech['return5Pct']) > 6:
        return dict(result, reasonZh='明显单边趋势，保留底仓不做T')
    vwap = finite(c.get('vwap'))
    if not vwap or vwap <= 0 or price < vwap + .5 * tech['atr14']:
        return result
    net_edge = (price / vwap - 1) * 100 - net_cost_pct
    if net_edge < .3 or net_edge < 1.5 * net_cost_pct:
        return dict(result, reasonZh='预期价差不足覆盖双边费用、冲击和安全余量')
    if not (b['price'] >= a['price'] and price < b['price'] * .998):
        return result
    return {'eligible': True, 'reasonZh': '震荡区冲高后转弱，净价差通过成本门槛',
            'targetBuyPrice': vwap, 'expectedNetEdgePct': round(net_edge, 3)}
