"""Point-in-time research rules. No broker, network, or accounting mutations."""
from __future__ import annotations

from datetime import datetime, time
from statistics import mean
from zoneinfo import ZoneInfo
from shadow_fund_v3 import finite

VERSION = 'v5.4-operational-continuity'
CN = ZoneInfo('Asia/Shanghai')
# Authoritative position bands from 市场情绪指数交易策略笔记.
# Values are fractions of total portfolio exposure.
POSITION_BANDS = {
    'LOW': (0.0, 0.20, 0.0),
    'MID': (0.20, 0.50, 0.50),
    'HIGH': (0.50, 0.80, 1.0),
    'OVERHEATED': (0.80, 1.01, 0.0),
}
PARAMETERS = {
    'singleLimit': .08, 'leaderLimit': .10, 'sectorLimit': .25,
    'correlationLimit': .35, 'normalTurnoverLimit': .20,
    'minCompleteHoldingDays': 2, 'targetConfirmations': 3,
    'initialEntryConfirmations': 1, 'rankingWarningPenalty': 3,
    'degradedEntryLimit': .01,
    'atrStopMultiple': 1.5, 'trailingAtrMultiple': 2.,
    'stopMin': .04, 'stopMax': .08, 'trailingActivation': .08,
    'profitTargetMin': .08, 'profitSecondMin': .15, 'profitZoneFraction': .99,
    'profitStallDrop': .002, 'profitMinReturn': .05,
    'tBaseFraction': .20, 'tNavLimit': .01, 'tMaxPairsPerDay': 1,
    'tMinNetEdge': .003, 'tMaxQuoteGapSeconds': 600,
    'parameterStatus': 'INITIAL_RESEARCH_NOT_OUT_OF_SAMPLE_VALIDATED',
}
RULES_ZH = {
    'newEntry': '大盘许可后按板块、资金和量价排序分批建仓。分数、排名、量比、阶段及回踩形态用于排序，不要求同时达标；可选数据不足或偏好未满足时首批单股≤1%。保留有效行情、可成交性、明确风险和组合仓位约束。',
    'position': '前一交易日四项掘金指数的综合市场资金情绪按方向型状态机决定次日基础仓位：0–20为0%，上升至20–50为50%，上升至50–80为100%，80以上为0%，回落至50–80为30%，回落至20–50为0%；盘中风险只能下调该上限。潜在主线初始2.5%，确认主线4%；普通单股≤8%，两次确认龙头≤10%，板块≤25%，相关板块≤35%。',
    'rotation': '现金不足时择优换仓：新票通过原买入条件及3轮确认；新旧证据完整，新旧优势再经3次间隔至少3分钟确认；评分优势≥10、近20日高点空间增益覆盖实际费用+0.86%滑点+1%余量，新票空间/风险≥1.5且较旧票高0.5。每天最多1项，单项≤净值5%、旧仓50%；先卖后买，15分钟内重新核验，失效保留现金；不绕过风控、T+1与容量。参数待样本外验证，价格空间不是预测收益。',
    'rebalance': '新仓及已确认余量在有效交易时段按排名执行，14:50后不新增；首批只需一个有效当前行情。普通加仓仍在10:00–10:30、14:30–14:50并确认3个不同快照。相同行情不重复买入；普通双边换手≤20%，仓位上限不要求立即买满。',
    'exit': '掉出候选只停加仓。至少2个完整交易日观察；1日失效观察，2日减半，3日退出；板块2日确认衰退退出。硬止损及组合风险优先，待退出数量不因T+1/跌停/部分成交丢失。',
    'stop': '1.5×ATR14/价格，距离限制4%–8%；ATR缺失保守4%并标注降级。盈利8%启动2×ATR移动保护；峰值盈利15%/25%后回撤距离上限收紧至5%/3%，风险线只收紧不放宽。',
    'profit': '主动止盈：首次获得完整日线时冻结目标一=max(20日高点,风险基准×1.08)，目标二=max(目标一×1.05,风险基准×1.15)。进入目标99%区间并经3个间隔3–10分钟快照确认滞涨回落≥0.2%，且当前盈利≥5%/10%，分别减1/3及剩余1/2；每档一次、每天一档。保护性卖出不等普通窗口/换手额度，保留T+1及成交限制。止盈当日禁止回补，已有T回补取消；参数待前向验证。',
    'execution': '持仓保护与慢证据采集独立运行；证据发布后触发交易检查，单一账本写入。新鲜行情与成交容量是执行依据；慢证据不足降低置信度和首批仓位，继续筛选。综合情绪研究分数未按时到达时，仅用前一交易日已验证宽度或核心指数生成0%/10%/20%保守运行上限，不冒充掘金指数。每次未买入必须列明具体执行障碍。',
    'defensive': '防守大盘仓位上限经2个间隔至少60秒的新鲜大盘快照确认后，立即分批降至上限，不受个股观察期、普通窗口及20%普通换手额度限制；指数急跌等紧急风险维持直接降仓。重复快照不累加；T+1/跌停/容量受限保留未成交数量。',
    'risk': '当日单位净值-1.5%停买，-2.5%总仓位目标降低25%；已确认日终净值回撤-5%仓位上限减半，-8%暂停新仓至少5个真实交易日并等待复核。',
    't': '主策略买卖优先；做T仅优化持仓期间成本，不延长持有。策略减仓/退出立即终止旧T回补，主策略确认买入不等待T配对。仅模拟先卖后买；每股每日最多1组，≤昨日底仓20%且≤净值1%。仅震荡且冲高转弱时卖，回落企稳才买回。强趋势、退出风险、缺行情、价差不足覆盖双边成本时不做T。未买回/部分买回也计入机会损益。',
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


def sentiment_position_cap(score, previous_score, previous_cap=None):
    """Direction-aware position table from 市场情绪指数交易策略笔记."""
    score, previous_score = finite(score), finite(previous_score)
    if score is None or not 0 <= score <= 100 or previous_score is None or not 0 <= previous_score <= 100:
        return {'ready': False, 'cap': 0., 'direction': 'UNKNOWN', 'reasonZh': '缺少连续两个交易日可用于仓位的综合情绪指数'}
    direction = 'RISING' if score > previous_score else 'FALLING' if score < previous_score else 'FLAT'
    if score < 20 or score >= 80:
        cap = 0.
    elif (20 <= score < 50 and 20 <= previous_score < 50) or (50 <= score < 80 and 50 <= previous_score < 80):
        cap = finite(previous_cap)
        if cap is None:
            return {'ready': False, 'cap': 0., 'direction': direction, 'reasonZh': '区间内缺少已确认状态，等待可审核跨档记录'}
    elif direction == 'RISING':
        cap = .5 if score < 50 else 1.
    elif direction == 'FALLING':
        cap = 0. if score < 50 else .3
    else:
        cap = finite(previous_cap, 0.)
    return {'ready': True, 'cap': cap, 'direction': direction, 'score': score,
            'previousScore': previous_score,
            'reasonZh': f'综合情绪{score:.2f}，方向{direction}，文件规则基础仓位{cap:.0%}'}


def market_regime(snapshot, now, macro=None, sentiment=None):
    sentiment = sentiment or {}
    base_cap = finite(sentiment.get('cap'), 0.) if sentiment.get('ready') else 0.
    result = {'state': 'UNKNOWN', 'cap': base_cap, 'baseCap': base_cap, 'intradayCap': None,
              'allowNew': False, 'reasonZh': sentiment.get('reasonZh') or '缺少前一交易日可用的综合情绪指数',
              'missingEvidence': [], 'sentiment': sentiment}
    if not sentiment.get('ready'):
        return result
    # Before the opening bell the audited previous-session decision is the
    # controlling risk budget. Same-day breadth does not exist yet; it may
    # only tighten this budget after 09:30.
    if now.time() < time(9, 30):
        return {'state': 'PREMARKET', 'cap': base_cap, 'baseCap': base_cap,
                'intradayCap': None, 'allowNew': base_cap > 0,
                'breadthPct': None, 'missingEvidence': [],
                'sentiment': sentiment, 'reasonZh': sentiment['reasonZh']}
    if not snapshot or snapshot.get('sourceDate') != now.date().isoformat() or not snapshot.get('verifiedToday'):
        return dict(result, state='BASELINE', allowNew=base_cap > 0,
                    reasonZh=result['reasonZh'] + '；盘中大盘证据尚未到达，维持盘前上限，不据缺失停买')
    if not fresh(snapshot.get('availableAt'), now, 900):
        return dict(result, state='BASELINE', allowNew=base_cap > 0,
                    reasonZh=sentiment.get('reasonZh', '') + '；盘中大盘快照过期/时间异常，维持盘前上限并等待新证据')
    values = [finite((snapshot.get('indices') or {}).get(k, {}).get('changePct'))
              for k in ('sh000001', 'sh000300', 'sz399006')]
    up, down = finite(snapshot.get('up')), finite(snapshot.get('down'))
    if any(x is None for x in values):
        return dict(result, state='BASELINE', allowNew=base_cap > 0,
                    reasonZh=sentiment.get('reasonZh', '') + '；核心指数数据未取齐，维持盘前上限')
    # Broad index crash still controls risk even if breadth is missing.
    avg = mean(values)
    if avg <= -2 or min(values) <= -3:
        return dict(result, state='RISK', cap=min(base_cap, .10), intradayCap=.10,
                    reasonZh='核心指数急跌，盘中风险上限下调至10%')
    if up is None or down is None or up + down < 2000:
        return dict(result, state='BASELINE', allowNew=base_cap > 0,
                    reasonZh=sentiment.get('reasonZh', '') + '；全市场广度未取齐，维持盘前上限，不用候选样本冒充')
    breadth = up / (up + down)
    if breadth < .25:
        state, intraday_cap = 'RISK', .10
    elif breadth < .4 or avg < -.8:
        state, intraday_cap = 'DEFENSIVE', .25
    else:
        state, intraday_cap = 'NORMAL', 1.
    # Macro inputs are evidence flags supplied as-of, never invented numeric weights.
    macro = macro or {}
    missing = [k for k in ('margin', 'broadEtf', 'usRisk', 'us30y', 'cn10y')
               if not isinstance(macro.get(k), dict) or not macro[k].get('verified')
               or not fresh(macro[k].get('availableAt'), now, 4 * 86400)]
    if any(x.get('riskOff') is True for k, x in macro.items() if isinstance(x, dict) and k not in missing):
        intraday_cap = min(intraday_cap, .25)
        state = 'DEFENSIVE'
    cap = min(base_cap, intraday_cap)
    return {'state': state, 'cap': cap, 'baseCap': base_cap, 'intradayCap': intraday_cap,
            'allowNew': state != 'RISK' and cap > 0,
            'breadthPct': round(breadth * 100, 2), 'missingEvidence': missing,
            'sentiment': sentiment,
            'reasonZh': f'{sentiment["reasonZh"]}；盘中广度{breadth:.1%}，实际仓位上限{cap:.0%}'}


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
        if (datetime.fromisoformat(today) - datetime.fromisoformat(etf_day)).days <= 7 and (not etf.get('availableAt') or (now and stamp(etf['availableAt']) and stamp(etf['availableAt']) <= now)):
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
        peak_gain = peak / basis - 1
        if peak_gain >= .25: trail_distance = min(trail_distance, .03)
        elif peak_gain >= .15: trail_distance = min(trail_distance, .05)
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


def confirmation_samples(samples):
    """Keep every raw observation; select time-spaced evidence ending at latest tick.

    Extra arrival-driven runs must not replace valid 3–10 minute evidence with
    three sub-minute ticks. No interpolation or bridging a missing collection window.
    """
    if len(samples) < 3: return samples
    c = samples[-1]
    for j in range(len(samples)-2, 0, -1):
        b = samples[j]
        gap = (stamp(c['at']) - stamp(b['at'])).total_seconds()
        if gap > 600: break
        if gap < 180: continue
        for i in range(j-1, -1, -1):
            a = samples[i]
            gap = (stamp(b['at']) - stamp(a['at'])).total_seconds()
            if gap > 600: break
            if gap >= 180:
                # Price setup still checks the actual sampled prices; do not
                # synthesize missing bars or bridge long collection outages.
                return [a, b, c]
    return samples[-3:]


def profit_signal(pos, price, technical, samples, now):
    """Freeze forward targets; emit at most one proposal per stage, never invent fills."""
    basis = finite(pos.get('riskBasis'), finite(pos.get('avgCost'), 0))
    if basis <= 0 or not technical.get('ready') or not finite(technical.get('high20'), 0):
        return None
    plan = pos.setdefault('profitPlan50', {})
    if not plan:
        first = max(technical['high20'], basis * 1.08)
        plan.update(activatedAt=now.isoformat(), target1=round(first, 4),
                    target2=round(max(first * 1.05, basis * 1.15), 4), queuedStages=[])
    stage = 1 if 1 not in plan['queuedStages'] else 2
    if stage in plan['queuedStages'] or plan.get('lastQueuedDay') == now.date().isoformat():
        return None
    if price < plan['target' + str(stage)] * .99 or price / basis - 1 < (.05 if stage == 1 else .10):
        return None
    recent = samples[-3:]
    if len(recent) != 3: return None
    times = [stamp(x.get('at')) for x in recent]
    if any(t is None or t < stamp(plan['activatedAt']) for t in times): return None
    if not all(180 <= (b-a).total_seconds() <= 600 for a,b in zip(times,times[1:])): return None
    if not fresh(recent[-1]['at'], now): return None
    values = [finite(x.get('price'), 0) for x in recent]
    if min(values) <= 0 or price != values[-1]: return None
    if values[-1] > values[0] or values[-1] > max(values) * .998: return None
    qty = int(pos['qty']) // (300 if stage == 1 else 200) * 100
    if qty <= 0: return None
    return {'stage': stage, 'qty': qty, 'targetPrice': plan['target' + str(stage)],
            'samples': recent, 'reasonZh': '目标区间滞涨转弱，主动止盈第%d档' % stage}
