"""Evidence-driven shadow-book state machine, with a separate sell-first T sleeve."""
from __future__ import annotations
from copy import deepcopy
from datetime import time
import math

import run_ai_shadow_portfolio as base
import run_ai_dynamic_portfolio_v2 as execution
import selection_rules_v45 as rules
import selection_data_v45 as feeds
import selection_research_v46 as study

CONTEXT = {}
LAST_ACTIONS = []
LAST_TARGETS = []
NO_T_CONTROL = False
CONTROL_MODE = None
ORIGINAL_QUOTES = base.fetch_tencent_quotes
ORIGINAL_BUILD = base.build_latest


def prepare_quotes(codes):
    stored = base.read_json(base.STATE_PATH, {})
    control = ((stored.get('research46') or {}).get('noTControl') or {}).get('state') or {}
    simple = ((stored.get('research46') or {}).get('timingControl') or {}).get('state') or {}
    codes = sorted(set(codes) | study.pending_codes(stored) | set(control.get('positions') or {}) | set(simple.get('positions') or {}))
    quotes = ORIGINAL_QUOTES(codes)
    radar = base.read_json(base.RADAR, {})
    state = base.read_json(base.STATE_PATH, base.new_state())
    now = base.now_cn()
    gateway = base.read_json(base.ROOT / 'astock_gateway/latest.json', {})
    market = gateway.get('marketSnapshot') or radar.get('marketSnapshot') or {}
    data = feeds.enrich(state, radar, quotes, now) if radar.get('date') == now.date().isoformat() else {}
    CONTEXT.clear()
    CONTEXT.update(radar=radar, quotes=quotes, data=data,
                   market=rules.market_regime(market, now, radar.get('macroEvidence')))
    return quotes


def metadata(state):
    obj = state.setdefault('selection45', {'activatedAt': base.iso(), 'version': rules.VERSION,
                                         'validationStatus': 'SHADOW_FORWARD_ONLY', 'pendingExits': {},
                                         'signals': {}, 'tCycles': [], 'audit': []})
    if CONTEXT.get('data'):
        state['selectionData45'] = CONTEXT['data']
    obj['market'] = CONTEXT.get('market') or {'state': 'UNKNOWN', 'cap': 0, 'allowNew': False, 'reasonZh': '无当日大盘证据'}
    return obj


def technical(state, code):
    return ((state.get('selectionData45') or {}).get('technical') or {}).get(code) or {}


def signal_stock(state, code, radar):
    stock = dict((radar.get('stocks') or {}).get(code) or {})
    pos = (state.get('positions') or {}).get(code) or {}
    sector = stock.get('sector') or pos.get('sector') or '未知'
    rank = (((state.get('selectionData45') or {}).get('sectorRanks') or {}).get(sector) or {})
    member = (rank.get('rows') or {}).get(code) or {}
    stock.update(member)
    stock.update(code=code, sector=sector, name=stock.get('name') or pos.get('name') or code)
    stock['sectorRank'] = (rank.get('ranks') or {}).get(code) if rank.get('complete') else None
    stock['rankSampleCount'] = rank.get('observed')
    stock['rankComplete'] = rank.get('complete', False)
    return stock


def sample(state, code, quotes):
    q = quotes.get(code) or {}
    now = base.now_cn()
    at = q.get('quoteTimestamp') or q.get('quoteTime')
    if not rules.fresh(at, now) or not rules.finite(q.get('price'), 0) > 0:
        return []
    stamp = rules.stamp(at, now.date().isoformat()).isoformat()
    samples = state.setdefault('selection45', {}).setdefault('samples', {}).setdefault(code, [])
    day = now.date().isoformat()
    samples[:] = [x for x in samples if x['at'][:10] == day]
    if not samples or stamp > samples[-1]['at']:
        amount, volume = rules.finite(q.get('amount')), rules.finite(q.get('volumeShares'))
        vwap = amount / volume if amount and volume else None
        samples.append({'at': stamp, 'price': q['price'], 'vwap': vwap})
        samples[:] = samples[-80:]
    return samples


def own_quote_ok(code):
    q = (CONTEXT.get('quotes') or {}).get(code) or {}
    return rules.fresh(q.get('quoteTimestamp') or q.get('quoteTime'), base.now_cn())


def annotate(state, row, reason_code, signal=None, sleeve='CORE'):
    if not row:
        return None
    row.update(ruleVersion=rules.VERSION, sleeve=sleeve, reasonCode=reason_code,
               signalSnapshot=deepcopy(signal or {}), effectiveFrom=state['selection45']['activatedAt'])
    return row


def turnover_room(state, ledger, nav):
    today = base.now_cn().date().isoformat()
    used = sum(float(x.get('amount') or 0) for x in ledger if str(x.get('date') or x.get('timestamp', '')[:10]) == today
               and x.get('reasonCode') not in ('HARD_STOP', 'TRAIL_STOP', 'PORTFOLIO_RISK', 'EMERGENCY_EXIT'))
    return max(0., nav * .20 - used)


def risk_control(state, prices):
    obj = metadata(state)
    nav, mv = base.portfolio_nav(state, prices)
    acc = base.fund.ensure_fund_accounting(state, nav)
    now = base.now_cn(); today = now.date().isoformat()
    history = base.fund.combined_unit_history(state, nav)
    # Only explicitly verified closing marks; never use the last intraday tick as a close.
    closes = {x['date']: x for x in history if x.get('isVerifiedClose') and x.get('date', '') < today}
    calendar = (state.get('selectionData45') or {}).get('marketSessions') or []
    previous_session = max((d for d in calendar if d < today), default=None)
    latest = closes[max(closes)]['unitNav'] if closes and (not previous_session or max(closes) == previous_session) else None
    daily = (acc['unitNav'] / latest - 1) if latest else None
    close_values = [closes[d]['unitNav'] for d in sorted(closes)]
    drawdown = close_values[-1] / max(close_values) - 1 if close_values else None
    market = obj['market']; cap = market['cap']
    # Missing breadth blocks buys but is not evidence to liquidate an existing book.
    if market['state'] == 'UNKNOWN':
        cap = max(cap, mv / nav if nav else 0)
    if drawdown is not None and drawdown <= -.05:
        cap *= .5
    guard = obj.setdefault('riskGuard', {})
    if drawdown is not None and drawdown <= -.08 and not guard.get('triggerDate'):
        guard.update(triggerDate=today, state='PAUSED_REVIEW_REQUIRED', observedTradingDays=[])
    if guard.get('triggerDate') and today > guard['triggerDate'] and base.trading_session(now) and any(own_quote_ok(c) for c in CONTEXT.get('quotes', {})):
        days = guard.setdefault('observedTradingDays', [])
        if today not in days:
            days.append(today)
    paused = bool(guard.get('triggerDate')) and (len(guard.get('observedTradingDays', [])) < 5 or not guard.get('reviewApprovedAt'))
    if daily is not None and daily <= -.025:
        guard.setdefault('dailyReduction', {}).setdefault(today, max(0., mv / nav * .75))
    cap = min(cap, guard.get('dailyReduction', {}).get(today, 1))
    result = {'cap': cap, 'allowNew': market['allowNew'] and not paused and (daily is None or daily > -.015),
              'date': today, 'asOf': base.iso(),
              'dailyUnitReturnPct': daily * 100 if daily is not None else None,
              'confirmedCloseDrawdownPct': drawdown * 100 if drawdown is not None else None,
              'dailyRiskDataReady': latest is not None, 'paused': paused,
              'forceReduction': market['state'] == 'RISK' or (daily is not None and daily <= -.025) or (drawdown is not None and drawdown <= -.05)}
    # Without a reliable daily base, opening new risk is blocked instead of assuming 0% loss.
    result['allowNew'] = result['allowNew'] and latest is not None
    obj['portfolioRisk'] = result
    return result


def queue_exit(state, pos, qty, code, reason, signal=None):
    if CONTROL_MODE == 'FIXED_HOLD' and code not in ('HARD_STOP', 'PORTFOLIO_RISK', 'CONFIRMED_EXPOSURE_REDUCTION', 'FIXED_HOLD_EXIT'):
        return
    obj = metadata(state); pending = obj.setdefault('pendingExits', {})
    old = pending.get(pos['code'])
    # A stronger full exit supersedes a partial order; never repeatedly halve each cycle.
    if old and old['remainingQty'] >= qty:
        return
    pending[pos['code']] = {'code': pos['code'], 'remainingQty': int(qty), 'requestedQty': int(qty),
                            'reasonCode': code, 'reasonZh': reason, 'createdAt': base.iso(),
                            'signal': deepcopy(signal or {}), 'state': 'PENDING'}


def execute_pending(state, ledger, prices):
    actions = []; now = base.now_cn(); today = now.date().isoformat()
    obj = metadata(state); pending = obj['pendingExits']
    for code, order in list(pending.items()):
        pos = state.get('positions', {}).get(code)
        if not pos:
            pending.pop(code, None); continue
        emergency = order['reasonCode'] in ('HARD_STOP', 'TRAIL_STOP', 'PORTFOLIO_RISK', 'EMERGENCY_EXIT')
        if not emergency and not rules.normal_window(now):
            continue
        if not own_quote_ok(code):
            order['state'] = 'WAIT_FRESH_QUOTE'; continue
        qty = min(order['remainingQty'], execution.sellable_qty(pos, today))
        if qty <= 0:
            order['state'] = 'WAIT_T_PLUS_ONE'; continue
        price = prices.get(code, pos.get('lastPrice', 0))
        if not emergency:
            nav, _ = base.portfolio_nav(state, prices)
            qty = min(qty, int(turnover_room(state, ledger, nav) / (price * 1.01) / 100) * 100)
        row = execution.reduce_or_sell(state, ledger, pos, qty, price, 0, order['reasonZh'])
        if row:
            annotate(state, row, order['reasonCode'], order['signal'])
            row['orderRequestedQty'] = order['requestedQty']
            order['remainingQty'] -= row['qty']; actions.append(row)
            if order['remainingQty'] <= 0:
                pending.pop(code, None)
            else:
                order['state'] = 'PARTIAL_WAIT'
        else:
            order['state'] = 'WAIT_CAPACITY_OR_LIMIT'
    return actions


def estimated_t_cost_pct(price, qty):
    amount = price * qty
    if amount <= 0: return 100.
    # Both legs at the maximum model slippage (spread 3 + impact 40 bps each).
    return (base.fees(amount, 'BUY') + base.fees(amount, 'SELL')) / amount * 100 + .86


def evaluate_t(state, ledger, prices, radar):
    if NO_T_CONTROL:
        return []
    obj = metadata(state); now = base.now_cn(); today = now.date().isoformat()
    actions = []; risk = risk_control(state, prices); quotes = CONTEXT.get('quotes') or {}
    cycles = obj['tCycles']; sectors = {x.get('name'): x for x in radar.get('mainlines') or []}
    # Close an existing pair only with new, independent evidence. A sell is never assumed to pair.
    for cycle in cycles:
        if cycle['status'] != 'OPEN': continue
        code = cycle['code']; remaining = cycle['remainingQty']
        if cycle['date'] < today or now.time() > time(14, 50):
            cycle['status'] = 'UNPAIRED'; cycle['reasonZh'] = '当日没有合格买回点，保留卖飞/部分买回损益'; continue
        pos = state.get('positions', {}).get(code)
        if code in obj['pendingExits'] or not pos or risk['forceReduction'] or risk['paused']:
            cycle['status'] = 'RISK_CANCELLED'; cycle['reasonZh'] = '风险退出优先，取消回补，保留相对持有损益'; continue
        if not risk['allowNew']:
            cycle['reasonZh'] = '大盘/净值证据暂未通过，等待恢复后再检查买回条件'; continue
        if not own_quote_ok(code): continue
        price = prices.get(code); samples = sample(state, code, quotes)
        stock = signal_stock(state, code, radar)
        y = stock.get('yunai') or {}
        if not price or not y.get('quoteOk') or not rules.fresh(y.get('quoteTime'), now) or not rules.finite(y.get('price'), 0) or abs(price / y['price'] - 1) > .003: continue
        sec = sectors.get(pos.get('sector')) or {}
        if sec.get('stage') not in ('EMERGING', 'CONFIRMING', 'ESTABLISHED'): continue
        if len(samples) < 3 or not all(180 <= (rules.stamp(b['at']) - rules.stamp(a['at'])).total_seconds() <= 600 for a, b in zip(samples[-3:-1], samples[-2:])): continue
        if not (samples[-2]['price'] >= samples[-3]['price'] * .999 and price > samples[-2]['price'] * 1.001): continue
        if price > cycle['targetBuyPrice'] or price <= pos.get('hardStopPrice', 0): continue
        nav, mv = base.portfolio_nav(state, prices)
        cw, sw, _ = base.current_weights(state, prices)
        room = min(float(state['cash']), turnover_room(state, ledger, nav),
                   max(0, risk['cap'] * nav - mv), max(0, (.08 - cw.get(code, 0)) * nav),
                   max(0, (.25 - sw.get(pos['sector'], 0)) * nav))
        group = pos.get('correlationGroup', 'UNVERIFIED_GROUP')
        group_value = sum(int(p['qty']) * prices.get(k, p.get('lastPrice', p['avgCost']))
                          for k, p in state.get('positions', {}).items() if p.get('correlationGroup', 'UNVERIFIED_GROUP') == group)
        room = min(room, max(0, .35 * nav - group_value))
        qty = min(remaining, int(room / (price * 1.01) / 100) * 100)
        if qty < 100: continue
        buy_plan = base.fund.plan_execution(state, side='BUY', code=code, name=pos['name'], requested_qty=qty,
                                           reference_price=price, market=base.EXECUTION_MARKET.get(code) or {}, day=today)
        if not buy_plan.get('allowed'): continue
        fill_qty = buy_plan['filledQty']; buy_amount = buy_plan['executionPrice'] * fill_qty
        proceeds_per_share = cycle['sellNetProceeds'] / cycle['soldQty']
        if (proceeds_per_share * fill_qty - buy_amount - base.fees(buy_amount, 'BUY')) / (price * fill_qty) < .003: continue
        target = {'code': code, 'name': pos['name'], 'sector': pos['sector'], 'score': pos.get('buyScore', 64),
                  'referencePrice': price, 'priceSource': '当时双源确认行情', 'reasonZh': '回落到预设区间且连续企稳',
                  'targetWeight': cw.get(code, 0), 'targetWeightPct': cw.get(code, 0) * 100}
        row = execution.add_or_buy(state, ledger, target, fill_qty, prices, '底仓做T买回')
        if not row: continue
        annotate(state, row, 'T_BUYBACK', {'cycleId': cycle['id'], 'targetBuyPrice': cycle['targetBuyPrice']}, 'T')
        row['tCycleId'] = cycle['id']
        cycle['remainingQty'] -= row['qty']
        cycle['boughtQty'] += row['qty']
        cycle['buyCost'] += row['amount'] + row['fee']
        cycle['fees'] += row['fee']
        cycle['realizedPairPnl'] = round(cycle['sellNetProceeds'] * cycle['boughtQty'] / cycle['soldQty'] - cycle['buyCost'], 2)
        cycle['buyDecisionIds'].append(row['decisionId'])
        if cycle['remainingQty'] <= 0:
            cycle['status'] = 'PAIRED'; cycle['closedAt'] = base.iso()
        actions.append(row)
    # Only initiate sell-first T after enough observations, preserving at least 80% of base.
    if not risk['allowNew'] or not (time(10, 15) <= now.time() <= time(14, 15)):
        return actions
    for code, pos in list(state.get('positions', {}).items()):
        if code in obj['pendingExits'] or any(x['code'] == code and x['date'] == today for x in cycles): continue
        if int(pos.get('completeObservedDays', 0)) < 2 or not own_quote_ok(code): continue
        if not technical(state, code).get('adv20'): continue
        stock = signal_stock(state, code, radar); y = stock.get('yunai') or {}
        price = prices.get(code, 0); sec = sectors.get(pos.get('sector')) or {}
        if sec.get('stage') not in ('CONFIRMING', 'ESTABLISHED') or rules.finite(stock.get('mainFlowPct'), -1) < 0: continue
        if not y.get('quoteOk') or not rules.fresh(y.get('quoteTime'), now) or not rules.finite(y.get('price'), 0) or not price or abs(price / y['price'] - 1) > .003: continue
        nav, _ = base.portfolio_nav(state, prices)
        daily = obj.setdefault('tBaseByDay', {}).setdefault(today, {})
        base_qty = daily.setdefault(code, execution.sellable_qty(pos, today))
        qty = min(int(base_qty * .2 / 100) * 100, int(nav * .01 / (price * 1.01) / 100) * 100,
                  execution.sellable_qty(pos, today), int(turnover_room(state, ledger, nav) / (2.02 * price) / 100) * 100)
        samples = sample(state, code, quotes)
        signal = rules.t_signal(price, technical(state, code), samples, estimated_t_cost_pct(price, qty))
        obj.setdefault('tSignals', {})[code] = dict(signal, code=code, name=pos['name'], at=base.iso(), maxQty=qty)
        if not signal['eligible'] or qty < 100: continue
        row = execution.reduce_or_sell(state, ledger, pos, qty, price, 0, '底仓做T：震荡冲高转弱，小比例卖出')
        if not row: continue
        cycle_id = 'T45-' + row['decisionId']
        annotate(state, row, 'T_SELL_FIRST', dict(signal, cycleId=cycle_id), 'T')
        row['tCycleId'] = cycle_id
        cycle = {'id': cycle_id, 'code': code, 'name': pos['name'], 'date': today, 'openedAt': base.iso(),
                 'status': 'OPEN', 'soldQty': row['qty'], 'remainingQty': row['qty'], 'boughtQty': 0,
                 'sellNetProceeds': row['amount'] - row['fee'], 'buyCost': 0., 'fees': row['fee'],
                 'targetBuyPrice': signal['targetBuyPrice'], 'realizedPairPnl': 0.,
                 'sellDecisionId': row['decisionId'], 'buyDecisionIds': [], 'reasonZh': signal['reasonZh']}
        cycles.append(cycle); actions.append(row)
    return actions


def freeze_daily_signals(state, radar, prices):
    obj = metadata(state); now = base.now_cn(); today = now.date().isoformat()
    if now.time() < time(15) or radar.get('date') != today: return
    captured = rules.stamp(radar.get('capturedAt'))
    if not captured or captured.date() != now.date() or captured.time() < time(15) or captured > now: return
    sectors = {x.get('name'): x for x in radar.get('mainlines') or []}
    for code, pos in state.get('positions', {}).items():
        track = obj.setdefault('holdingSignals', {}).setdefault(code, {'completedDays': [], 'daily': {}})
        if today in track['daily']: continue
        stock = signal_stock(state, code, radar); sec = sectors.get(pos.get('sector')) or {}
        tech = technical(state, code); q = (CONTEXT.get('quotes') or {}).get(code) or {}
        qt = rules.stamp(q.get('quoteTime'))
        if not qt or qt.date() != now.date() or qt.time() < time(15): continue
        flow = rules.finite(stock.get('mainFlowPct')); breadth = rules.finite(sec.get('breadthPct'))
        rel = rules.finite(stock.get('changePct'))
        sec_change = rules.finite(sec.get('changePct'))
        valid = flow is not None and tech.get('ready') and rel is not None and sec_change is not None
        stock_bad = q['price'] < tech.get('ma20', 0) and flow < 0 and rel - sec_change < -1 if valid else None
        negative = int(flow is not None and flow < 0) + int(breadth is not None and breadth < 40)
        margin = stock.get('marginData') or {}
        if margin.get('dataDate', today) < today and rules.finite(margin.get('balanceChange1d'), 0) < 0: negative += 1
        sector_bad = sec.get('stage') in ('DECAY', 'DECLINING', 'FADING') and negative >= 2 if sec else None
        track['daily'][today] = {'stockInvalid': stock_bad, 'sectorInvalid': sector_bad,
                                  'capturedAt': base.iso(), 'dataComplete': valid,
                                  'reasonZh': '缺失数据为未知，不当成失效' if not valid else '收盘量价资金与相对板块确认'}


def t_report(state, prices):
    obj = metadata(state); cycles = deepcopy(obj['tCycles'])
    complete, unpaired, missing_marks = 0, 0, 0; paired_pnl = 0.; opportunity_pnl = 0.
    for cycle in cycles:
        paired_pnl += cycle['realizedPairPnl']
        if cycle['status'] == 'PAIRED': complete += 1
        if cycle['remainingQty']:
            unpaired += 1
            price = prices.get(cycle['code']) or (state.get('positions', {}).get(cycle['code']) or {}).get('lastPrice')
            mark = ((cycle['sellNetProceeds'] / cycle['soldQty'] - price) * cycle['remainingQty']) if price else None
            if mark is None: missing_marks += 1
            cycle['unpairedOpportunityPnl'] = round(mark, 2) if mark is not None else None
            opportunity_pnl += mark or 0
    return {'mode': 'SIMULATED_SELL_FIRST', 'validationStatus': 'UNVALIDATED_FORWARD_RESEARCH',
            'pairedCount': complete, 'unpairedCount': unpaired, 'pairedNetPnl': round(paired_pnl, 2),
            'unpairedOpportunityPnl': round(opportunity_pnl, 2),
            'incrementalPnlVsUnchangedShares': round(paired_pnl + opportunity_pnl, 2) if missing_marks == 0 else None,
            'missingMarkCount': missing_marks,
            'totalFees': round(sum(x['fees'] for x in cycles), 2), 'cycles': cycles,
            'signals': list(obj.get('tSignals', {}).values()),
            'noteZh': '配对净收益已扣实际费用和成交滑点；未配对部分按卖出净额减现价持有价值计机会损益。仅做T股数的局部持有对照，不是完整策略回测；不重复计入净值或改写会计成本。'}


def build_latest(state, ledger, prices, radar):
    obj = metadata(state)
    if radar.get('date') != base.now_cn().date().isoformat() or not CONTEXT.get('quotes'):
        obj['portfolioRisk'] = dict(obj.get('portfolioRisk') or {}, allowNew=False,
                                    currentEvidenceReady=False)
    for cycle in obj['tCycles']:
        if cycle['status'] == 'OPEN' and (cycle['date'] < base.now_cn().date().isoformat() or base.now_cn().time() > time(14, 50)):
            cycle.update(status='UNPAIRED', reasonZh='当日未完成买回，保留全部未配对机会损益')
    freeze_daily_signals(state, CONTEXT.get('radar') or radar, prices)
    # Snapshot current closing NAV only after verified full current holding quotes at close.
    now = base.now_cn(); today = now.date().isoformat()
    held = state.get('positions') or {}
    quotes = CONTEXT.get('quotes') or {}
    close_ok = now.time() >= time(15) and radar.get('date') == today and all(
        (rules.stamp((quotes.get(c) or {}).get('quoteTime')) is not None
         and rules.stamp(quotes[c]['quoteTime']).date() == now.date()
         and rules.stamp(quotes[c]['quoteTime']).time() >= time(15)) for c in held)
    if close_ok:
        for point in reversed(state.get('navHistory') or []):
            if point.get('date') == today and point.get('timestamp') == base.iso():
                point['isVerifiedClose'] = True; break
    comparison = update_no_t_control(state, ledger, prices, radar, close_ok)
    simple_comparison = update_no_t_control(state, ledger, prices, radar, close_ok, 'timingControl', 'FIXED_HOLD')
    study.mark_cohorts(state, quotes, now)
    out = ORIGINAL_BUILD(state, ledger, prices, radar)
    out.update(strategyVersion=rules.VERSION, mode='a股筛选池 · 主线持仓＋底仓T研究', simulated=True)
    out.setdefault('rulesZh', {}).update(rules.RULES_ZH)
    verified_history = [x for x in base.fund.combined_unit_history(state) if x.get('isVerifiedClose')]
    strict_daily = base.fund.daily_unit_series(verified_history)
    verified_closes = [x['closeUnitNav'] for x in strict_daily]
    out['legacyReportedMaxDrawdownPct'] = out.get('summary', {}).get('maxDrawdownPct')
    out['legacyDailyPerformance'] = out.get('dailyPerformance', [])
    out['dailyPerformance'] = strict_daily
    out['summary']['maxDrawdownPct'] = base.fund.max_drawdown(verified_closes) if verified_closes else None
    out['summary']['formalCloseSampleDays'] = len(strict_daily)
    risk_snapshot = obj.get('portfolioRisk') or {}
    out['summary']['todayReturnPct'] = risk_snapshot.get('dailyUnitReturnPct') if risk_snapshot.get('date') == today else None
    out['weeklyPerformance'] = base.fund._period_series(strict_daily, 'week')
    out['monthlyPerformance'] = base.fund._period_series(strict_daily, 'month')
    report = out.get('performanceReport') or {}
    if 'risk' in report:
        report['risk'].update(base.fund.risk_metrics(strict_daily))
        report['risk']['dailyCloseMaxDrawdownPct'] = out['summary']['maxDrawdownPct']
        report['risk']['closeVerificationNoteZh'] = '仅使用确认的日终估值；旧版盘中替代收盘统计另列保留'
    if 'returns' in report:
        report['returns'].update(daily=strict_daily, weekly=out['weeklyPerformance'], monthly=out['monthlyPerformance'])
    out['selection45'] = {k: deepcopy(obj.get(k)) for k in ('activatedAt', 'validationStatus', 'market', 'portfolioRisk')}
    out['selection45'].update(parameters=rules.PARAMETERS,
                              pendingExits=list(obj['pendingExits'].values()),
                              candidates=list(obj.get('signals', {}).values()),
                              holdingSignals=deepcopy(obj.get('holdingSignals', {})))
    elapsed = sum(d > obj['activatedAt'][:10] for d in (state.get('selectionData45') or {}).get('marketSessions', []))
    out['selection45']['nextReview'] = {'observedTradingDays': elapsed, 'reviewEveryTradingDays': 20,
                                       'reviewDue': elapsed >= 20,
                                       'statusZh': '已到滚动复核窗口，须样本外检查' if elapsed >= 20 else '正在积累前向影子盘样本；尚不能判断优于旧策略'}
    out['tTrading'] = t_report(state, prices)
    out['strategyResearch'] = study.report(state, now, comparison, simple_comparison)
    out['targetPortfolio'] = [{k: t[k] for k in ('code', 'name', 'sector', 'score', 'targetWeightPct', 'referencePrice', 'priceSource', 'reasonZh')}
                              for t in LAST_TARGETS if not t['rejections']]
    out['targetGrossPct'] = round(sum(x['targetWeightPct'] for x in out['targetPortfolio']), 2)
    out['decisionCycle'] = {'frequencyZh': '每5分钟监控；固定窗口普通交易；缺失数据拒绝新增风险',
                            'actionsThisCycle': len(LAST_ACTIONS), 'singleStockLimitPct': 8,
                            'sectorLimitPct': 25, 'grossLimitPct': 100,
                            'executionModel': 'v3-liquidity-capacity-point-in-time'}
    for row in out.get('positions') or []:
        pos = held.get(row.get('code'), {})
        row['decisionPlan'] = study.holding_plan(pos, obj['pendingExits'].get(row.get('code')), own_quote_ok(row.get('code')))
        row['currentActionZh'] = row['decisionPlan']['actionZh']
        row.update({k: pos.get(k) for k in ('holdingState', 'hardStopPrice', 'trailingStopPrice',
                                           'atrFallback', 'completeObservedDays', 'invalidDayStreak')})
    return out


def main():
    base.STRATEGY_VERSION = rules.VERSION
    base.MAX_SINGLE_WEIGHT = .08
    base.MAX_SECTOR_WEIGHT = .25
    base.fetch_tencent_quotes = prepare_quotes
    base.evaluate_exits = evaluate_exits
    base.evaluate_entries = evaluate_entries
    base.build_latest = build_latest
    return base.main()


def evaluate_exits(state, ledger, radar_stocks, quotes, prices):
    global LAST_ACTIONS
    if not NO_T_CONTROL and all(own_quote_ok(c) for c in state.get('positions') or {}):
        start_no_t_control(state, ledger, prices)
    obj = metadata(state); now = base.now_cn(); today = now.date().isoformat()
    radar = CONTEXT.get('radar') or {'stocks': radar_stocks}
    sectors = {x.get('name'): x for x in radar.get('mainlines') or []}
    risk = risk_control(state, prices)
    nav, mv = base.portfolio_nav(state, prices)
    # Market-cap reductions also require distinct observations, never candidate absence.
    cap_confirmation = obj.setdefault('capConfirmation', {})
    cap_at = rules.stamp(radar.get('capturedAt'))
    cap_before = rules.stamp(cap_confirmation.get('at'))
    if cap_confirmation.get('cap') != risk['cap'] or (cap_before and cap_at and (cap_at - cap_before).total_seconds() > 900):
        cap_confirmation.clear(); cap_before = None
    if cap_at and (not cap_before or (cap_at - cap_before).total_seconds() >= 180):
        cap_confirmation.update(at=cap_at.isoformat(), cap=risk['cap'], count=cap_confirmation.get('count', 0) + 1)
    cw, sw, _ = base.current_weights(state, prices)
    for code, pos in list(state.get('positions', {}).items()):
        pos['invalidationZh'] = '硬止损、日级连续失效、板块确认衰退或组合风险；掉榜不卖'
        pos['expectedHorizonZh'] = '至少观察2个完整交易日；第3/5/10交易日复核，不机械换仓'
        if not own_quote_ok(code):
            continue
        price = prices.get(code) or quotes[code]['price']
        pos.update(rules.stop_lines(pos, price, technical(state, code)))
        pos['lastPrice'] = price; pos['lastPriceAt'] = base.iso()
        sample(state, code, quotes)
        tracked = obj.setdefault('holdingSignals', {}).setdefault(code, {'completedDays': [], 'daily': {}})
        # Daily streak derives only from frozen closing snapshots, not number of jobs.
        calendar = (state.get('selectionData45') or {}).get('marketSessions') or []
        valid_days = sorted(d for d in calendar if pos.get('entryDate', today) < d < today)
        completed = len(valid_days)
        streak = 0; sector_streak = 0
        for d in reversed(valid_days):
            if tracked['daily'].get(d, {}).get('stockInvalid') is True: streak += 1
            else: break
        for d in reversed(valid_days):
            if tracked['daily'].get(d, {}).get('sectorInvalid') is True: sector_streak += 1
            else: break
        pos['holdingState'] = 'OBSERVE' if streak == 1 else 'HOLD'
        pos['completeObservedDays'] = completed
        pos['invalidDayStreak'] = streak
        pos['nextReviewDay'] = next((d for d in (3, 5, 10) if d > completed), None)
        qty = int(pos['qty'])
        if price <= pos['hardStopPrice']:
            queue_exit(state, pos, qty, 'HARD_STOP', 'ATR保护性止损触发', {'stopPrice': pos['hardStopPrice'], 'atrFallback': pos['atrFallback']})
        elif pos['trailingStopPrice'] and price <= pos['trailingStopPrice']:
            # Confirmed trailing breach enters staged execution; capacity handles fractions.
            queue_exit(state, pos, qty, 'TRAIL_STOP', '盈利后移动保护触发', {'stopPrice': pos['trailingStopPrice']})
        elif completed >= 2 and sector_streak >= 2:
            queue_exit(state, pos, qty, 'SECTOR_DECAY', '板块衰退且至少两项证据恶化，连续2个日终确认')
        elif completed >= 2 and streak >= 3:
            queue_exit(state, pos, qty, 'STOCK_INVALID_3D', '个股连续3个日终信号失效，退出')
        elif completed >= 2 and streak >= 2 and tracked.get('trimmedStreakStart') != valid_days[-streak]:
            queue_exit(state, pos, qty // 200 * 100, 'STOCK_INVALID_2D', '个股连续2个日终信号失效，减仓50%')
            tracked['trimmedStreakStart'] = valid_days[-streak]
        stock = signal_stock(state, code, radar)
        sec = sectors.get(pos.get('sector')) or {}
        flow = rules.finite(stock.get('mainFlowPct'))
        relative = rules.finite(stock.get('changePct'), 0) - rules.finite(sec.get('changePct'), 0)
        if flow is not None and flow <= -8 and relative <= -2 and completed >= 2 and tracked.get('fastTrimDay') != today:
            queue_exit(state, pos, qty // 200 * 100, 'FAST_FLOW_FAILURE', '资金快速转负且明显弱于板块，减半')
            tracked['fastTrimDay'] = today
        if sec.get('stage') == 'OVERHEATED' and flow is not None and flow <= 0 and completed >= 2 and not tracked.get('overheatTrimmed'):
            queue_exit(state, pos, qty // 300 * 100, 'OVERHEAT_TRIM', '板块过热且个股资金未跟随，减仓三分之一')
            tracked['overheatTrimmed'] = True
        if risk['forceReduction'] and mv > nav * risk['cap'] and mv > 0:
            fraction = min(1, max(0, 1 - nav * risk['cap'] / mv))
            queue_exit(state, pos, math.ceil(qty * fraction / 100) * 100, 'PORTFOLIO_RISK', '组合风险优先降仓', risk)
        elif completed >= 2 and obj['market']['state'] != 'UNKNOWN' and cap_confirmation.get('count', 0) >= 3:
            gross_fraction = max(0., 1 - nav * risk['cap'] / mv) if mv and mv / nav - risk['cap'] >= .03 else 0.
            single_fraction = max(0., 1 - .08 / cw[code]) if cw.get(code, 0) - .08 >= .03 else 0.
            sector_weight = sw.get(pos.get('sector'), 0)
            sector_fraction = max(0., 1 - .25 / sector_weight) if sector_weight - .25 >= .03 else 0.
            fraction = max(gross_fraction, single_fraction, sector_fraction)
            if fraction > 0:
                queue_exit(state, pos, int(qty * fraction / 100) * 100, 'CONFIRMED_EXPOSURE_REDUCTION',
                           '大盘/集中度上限连续3轮确认，固定窗口分批降仓', risk)
    if CONTROL_MODE == 'FIXED_HOLD':
        for pos in state.get('positions', {}).values():
            if pos.get('completeObservedDays', 0) >= 10:
                queue_exit(state, pos, int(pos['qty']), 'FIXED_HOLD_EXIT', '简单基线：持仓起始日起满10个完整交易日退出')
    LAST_ACTIONS = execute_pending(state, ledger, prices)
    return list(LAST_ACTIONS)


def build_candidate(state, stock, radar, quotes):
    code = stock['code']; now = base.now_cn(); today = now.date().isoformat()
    q = quotes.get(code) or {}; rejects = []; reasons = []
    sec = next((x for x in radar.get('mainlines') or [] if x.get('name') == stock.get('sector')), {})
    stage = sec.get('stage')
    evidence = rules.sector_evidence(stock, sec, today, now)
    if stage not in ('EMERGING', 'CONFIRMING'): rejects.append('板块不处于潜在/确认阶段')
    if len(evidence) < 2 or not set(evidence) & {'B1', 'B2', 'B3'}: rejects.append('板块独立证据不足两类或缺资金')
    if not own_quote_ok(code): rejects.append('主行情缺失/过期')
    y = stock.get('yunai') or {}
    if not y.get('quoteOk') or not rules.fresh(y.get('quoteTime'), now): rejects.append('第二行情缺失/过期')
    price = rules.finite(q.get('price'), 0)
    if not price or not rules.finite(y.get('price'), 0) or abs(price / y['price'] - 1) > .003:
        rejects.append('双源价格偏差超过0.3%或缺数')
    if 'ST' in stock.get('name', '').upper() or '退' in stock.get('name', '') or stock.get('suspended'):
        rejects.append('风险警示/退市/停牌禁止买入')
    if stock.get('sectorRank') is None or stock['sectorRank'] > .2: rejects.append('未验证板块完整样本前20%')
    score, old_reasons, old_rejects = base.score_candidate(dict(stock, mainlineStage=stage))
    reasons.extend(old_reasons); rejects.extend(old_rejects)
    if score < 64: rejects.append('综合分不足64')
    change = rules.finite(q.get('changePct'))
    if change is None or change > 3.5 or change < -2.5: rejects.append('涨跌幅超出保守买入区间')
    tech = technical(state, code)
    ratio = tech.get('volumeRatio5to20')
    if ratio is None or not 1.2 <= ratio <= 2.5: rejects.append('完整5/20日成交额量比未通过1.2–2.5')
    if not tech.get('adv20'): rejects.append('ADV20不足20个完整交易日')
    samples = sample(state, code, quotes)
    setup = rules.price_setup(price, tech, samples) if price else {'ready': False, 'reasonZh': '无价格'}
    if not setup['ready'] and CONTROL_MODE != 'FIXED_HOLD': rejects.append(setup['reasonZh'])
    # Sector-relative 5-day data must be explicitly supplied; cannot substitute daily change.
    sector_r5 = rules.finite(sec.get('return5Pct'))
    if sector_r5 is None: rejects.append('板块5日收益缺失，无法检查相对涨幅')
    elif rules.finite(tech.get('return5Pct'), 99) - sector_r5 > 5: rejects.append('5日相对板块扩张超过5个百分点')
    cost_pct = (base.fees(max(10000, price * 1000), 'BUY') + base.fees(max(10000, price * 1000), 'SELL')) / max(10000, price * 1000) * 100 + .8
    # .8% is the maximum two-leg impact+spread allowance of the conservative model.
    if CONTROL_MODE != 'FIXED_HOLD' and setup.get('ready') and setup.get('potentialRewardPct', 0) < cost_pct + .3: rejects.append('近期阻力位空间不足覆盖双边成本及余量')
    target = .025 if stage == 'EMERGING' else .04
    pos = (state.get('positions') or {}).get(code)
    if pos:
        pending = (state.get('selection45', {}).get('pendingBuys') or {}).get(code)
        if pending:
            target = pending['targetWeight']
        else:
            if int(pos.get('completeObservedDays', 0)) < 2: rejects.append('尚未经过2个完整交易日观察，不加仓')
            if pos.get('addCount45', 0) >= 2: rejects.append('已达到最多两次加仓')
            if price <= rules.finite(pos.get('lastCoreBuyPrice'), rules.finite(pos.get('entryPrice'), price)): rejects.append('价格未改善，禁止下跌摊平')
            target = min(.08, max(.04, float(pos.get('coreTargetWeight45', .04)) + .03))
            if stage != 'CONFIRMING': rejects.append('加仓要求板块确认')
    return {'code': code, 'name': stock['name'], 'sector': stock['sector'], 'score': score,
            'referencePrice': price, 'priceSource': '当时双源确认行情', 'reasonZh': '；'.join(reasons + [setup.get('reasonZh', '')]),
            'targetWeight': target, 'targetWeightPct': target * 100, 'stage': stage,
            'evidence': evidence, 'setup': setup, 'technical': tech, 'rejections': sorted(set(rejects)),
            'rankSampleCount': stock.get('rankSampleCount'), 'sectorRank': stock.get('sectorRank'), 'dataAt': base.iso()}


def evaluate_entries(state, ledger, radar, prices):
    global LAST_TARGETS, LAST_ACTIONS
    obj = metadata(state); now = base.now_cn(); quotes = CONTEXT.get('quotes') or {}
    risk = risk_control(state, prices); actions = []
    enriched_radar = CONTEXT.get('radar') or radar
    targets = [build_candidate(state, signal_stock(state, code, enriched_radar), enriched_radar, quotes) for code in radar.get('stocks') or {}]
    targets.sort(key=lambda x: x['score'], reverse=True)
    LAST_TARGETS = targets
    for target in targets:
        target['decisionPlan'] = study.entry_plan(target)
    obj['signals'] = {t['code']: t for t in targets}
    if not NO_T_CONTROL:
        study.freeze_candidates(state, targets, enriched_radar, quotes, now)
    confirmations = obj.setdefault('confirmations', {})
    pending_core = obj.setdefault('pendingBuys', {})
    for t in targets:
        code = t['code']; c = confirmations.setdefault(code, {})
        if t['rejections'] or not risk['allowNew']:
            c.clear(); pending_core.pop(code, None); continue
        # Target confirmation counts unique timestamped observations separated >=3 minutes.
        at = rules.stamp((quotes.get(code) or {}).get('quoteTime'))
        previous = rules.stamp(c.get('at'))
        weight = t['targetWeight']
        if c.get('weight') != weight or (previous and at and (at - previous).total_seconds() > 900): c.clear()
        if at and (not previous or (at - previous).total_seconds() >= 180):
            c.update(at=at.isoformat(), weight=weight, count=int(c.get('count', 0)) + 1)
        if c.get('count', 0) < 3 or not rules.normal_window(now) or code in obj['pendingExits']:
            continue
        pos = state.get('positions', {}).get(code)
        if any(x['code'] == code and x.get('remainingQty', 0) > 0 and x['status'] == 'OPEN' for x in obj['tCycles']):
            continue
        nav, mv = base.portfolio_nav(state, prices)
        cw, sw, _ = base.current_weights(state, prices)
        delta = weight - cw.get(code, 0)
        if pos and delta < .03 - 1e-7 and code not in pending_core: continue
        # Unknown correlation groups are conservatively treated as one group.
        group = t.get('correlationGroup', 'UNVERIFIED_GROUP')
        group_value = sum(int(p['qty']) * prices.get(k, p.get('lastPrice', p['avgCost']))
                          for k, p in state.get('positions', {}).items() if p.get('correlationGroup', 'UNVERIFIED_GROUP') == group)
        cash = float(state.get('cash', 0)); price = t['referencePrice']
        room = min(max(0, delta * nav), max(0, risk['cap'] * nav - mv),
                   max(0, (.25 - sw.get(t['sector'], 0)) * nav), max(0, .35 * nav - group_value),
                   turnover_room(state, ledger, nav), cash)
        qty = int(room / (price * 1.01) / 100) * 100 if price else 0
        if qty < 100: continue
        pending_core.setdefault(code, {'targetWeight': weight, 'startedAt': base.iso(), 'isAdd': bool(pos)})
        order = pending_core[code]
        reason = '简单持有对照：首个可行窗口建仓/加仓' if CONTROL_MODE == 'FIXED_HOLD' else '回撤确认后的分批建仓/加仓'
        row = execution.add_or_buy(state, ledger, t, qty, prices, reason)
        if row:
            annotate(state, row, 'SIMPLE_ENTRY' if CONTROL_MODE == 'FIXED_HOLD' else 'CONFIRMED_ENTRY', t)
            new_pos = state['positions'][code]
            if not order.get('counted'):
                if order['isAdd']: new_pos['addCount45'] = int(new_pos.get('addCount45', 0)) + 1
                order['counted'] = True
            new_pos.update(coreTargetWeight45=weight, lastCoreBuyPrice=price,
                           correlationGroup=group, riskBasis=max(new_pos.get('riskBasis', 0), new_pos['avgCost']))
            # Target remains fixed across partial fills, then confirmation restarts for any later add.
            if state['positions'][code]['qty'] * price >= weight * nav - price * 100 * 1.01:
                pending_core.pop(code, None); c.clear()
            actions.append(row)
    actions.extend(evaluate_t(state, ledger, prices, radar))
    LAST_ACTIONS += actions
    return actions


def start_no_t_control(state, ledger, prices):
    obj = study.research(state, base.now_cn())
    if obj.get('noTControl'):
        return
    book = deepcopy({k: v for k, v in state.items() if k != 'research46'})
    # Equal cash/positions at activation. Historical T effects before activation stay in both books.
    selection = book.setdefault('selection45', {})
    selection['tCycles'] = []
    selection['tSignals'] = {}
    nav, _ = base.portfolio_nav(state, prices)
    units = base.fund.ensure_fund_accounting(state, nav)['unitNav']
    control_units = base.fund.ensure_fund_accounting(book, nav)['unitNav']
    obj['noTControl'] = {'startedAt': base.iso(), 'state': book, 'ledger': deepcopy(ledger),
        'initialLedgerCount': len(ledger), 'primaryStartUnitNav': units,
        'controlStartUnitNav': control_units, 'closeHistory': [],
        'capitalEventsHash': study.digest(state.get('capitalEvents') or [])}
    obj['timingControl'] = deepcopy(obj['noTControl'])


def update_no_t_control(state, ledger, prices, radar, primary_close_ok, control_key='noTControl', mode='NO_T'):
    global NO_T_CONTROL, LAST_ACTIONS, LAST_TARGETS, CONTROL_MODE
    obj = study.research(state, base.now_cn()); control = obj.get(control_key)
    if not control:
        return {'statusZh': '等待下一次有效交易时点初始化同起点对照', 'closeSampleDays': 0}
    if control['capitalEventsHash'] != study.digest(state.get('capitalEvents') or []):
        return {'statusZh': '资金事件改变，暂停对比并等待核对两组现金流', 'closeSampleDays': len(control['closeHistory'])}
    now = base.now_cn(); quotes = CONTEXT.get('quotes') or {}
    book = control['state']; book_ledger = control['ledger']
    # One immutable input cycle, independently sized/filled core orders and independent cash.
    book['selectionData45'] = deepcopy(state.get('selectionData45') or {})
    enriched = CONTEXT.get('radar') or radar
    mark_prices = dict(prices)
    for code in book.get('positions') or {}:
        p = study.quote_price(quotes.get(code) or {}, now)
        if p: mark_prices[code] = p
        base.EXECUTION_MARKET[code] = base.fund.market_data(
            (enriched.get('stocks') or {}).get(code) or {}, quotes.get(code) or {},
            (book['positions'][code]).get('lastPrice'))
    captured = enriched.get('capturedAt')
    ready = base.trading_session(now) and base.radar_freshness(enriched, now)[0]
    saved = (LAST_ACTIONS, LAST_TARGETS, NO_T_CONTROL, CONTROL_MODE)
    try:
        NO_T_CONTROL = True
        CONTROL_MODE = mode
        if ready and control.get('lastCycleAt') != base.iso(now):
            base.fund.update_liquidity_profiles(book, enriched, quotes, now.date().isoformat())
            evaluate_exits(book, book_ledger, enriched.get('stocks') or {}, quotes, mark_prices)
            evaluate_entries(book, book_ledger, enriched, mark_prices)
            control['lastCycleAt'] = base.iso(now)
        freeze_daily_signals(book, enriched, mark_prices)
    finally:
        LAST_ACTIONS, LAST_TARGETS, NO_T_CONTROL, CONTROL_MODE = saved
    nav, mv = base.portfolio_nav(book, mark_prices)
    units = base.fund.ensure_fund_accounting(book, nav)['unitNav']
    primary_nav, _ = base.portfolio_nav(state, prices)
    primary_units = base.fund.ensure_fund_accounting(state, primary_nav)['unitNav']
    close_ok = primary_close_ok and all(study.quote_price(quotes.get(c) or {}, now, True) for c in book.get('positions') or {})
    if close_ok:
        point = {'date': now.date().isoformat(), 'timestamp': base.iso(now), 'nav': nav,
                 'unitNav': units, 'isVerifiedClose': True, 'cash': book['cash'], 'marketValue': mv}
        history = book.setdefault('navHistory', [])
        if not history or history[-1].get('timestamp') != point['timestamp']:
            history.append(point)
        closes = control['closeHistory']
        row = {'date': point['date'], 'withT': primary_units / control['primaryStartUnitNav'],
               'withoutT': units / control['controlStartUnitNav']}
        if closes and closes[-1]['date'] == row['date']:
            closes[-1] = row
        else:
            closes.append(row)
    closes = control['closeHistory']; last = closes[-1] if closes else {}
    new_rows = book_ledger[control['initialLedgerCount']:]
    return {'statusZh': '积累同起点独立无T对照' if closes else '已初始化，等待两组完整收盘估值',
        'startedAt': control['startedAt'], 'closeSampleDays': len(closes),
        'asOfDate': last.get('date'),
        'withTReturnPct': (last['withT'] - 1) * 100 if last else None,
        'withoutTReturnPct': (last['withoutT'] - 1) * 100 if last else None,
        'incrementalReturnPp': (last['withT'] - last['withoutT']) * 100 if last else None,
        'withTDrawdownPct': base.fund.max_drawdown([1.] + [x['withT'] for x in closes]) if closes else None,
        'withoutTDrawdownPct': base.fund.max_drawdown([1.] + [x['withoutT'] for x in closes]) if closes else None,
        'controlFees': sum(rules.finite(x.get('fee'), 0) for x in new_rows),
        'controlPositionCount': len(book.get('positions') or {}),
        'noteZh': '自启用起相同资金和持仓，独立执行同一核心买卖及风控，仅关闭做T；使用确认收盘单位净值，包含费用、滑点与卖飞影响。未验证长期增益。'}
