"""Cash-funded opportunity replacement. Only forward shadow fills, never synthetic sales."""
from copy import deepcopy
from datetime import timedelta, time
import selection_rules_v45 as rules

PARAMETERS = dict(scoreGap=10., spaceMarginPct=1., rewardRiskGap=.5,
                  minRewardRisk=1.5, pairConfirmations=3, maxNavFraction=.05, maxDonorFraction=.5,
                  maxPlansPerDay=1, maxAgeMinutes=15, maxPriceRisePct=1.,
                  status='INITIAL_RESEARCH_NOT_OUT_OF_SAMPLE_VALIDATED')
TERMINAL = {'DONE', 'CANCELLED', 'EXPIRED'}


def active(obj):
    plan = (obj.get('rotation49') or {}).get('active')
    return plan if plan and plan.get('status') not in TERMINAL else None


def edge(buyer, donor, amount, fees):
    """Historical resistance space is a price reference, not an expected return forecast."""
    def metrics(t):
        price = rules.finite(t.get('referencePrice'), 0)
        tech = t.get('technical') or {}
        if not price or not tech.get('ready') or not rules.finite(tech.get('adv20'), 0): return None
        high = rules.finite(tech.get('high20'), 0)
        atr = rules.finite(tech.get('atr14'), 0)
        if not high or not atr: return None
        reward = max(0., high / price - 1) * 100
        risk = min(8., max(4., 1.5 * atr / price * 100))
        return reward, reward / risk
    b, d = metrics(buyer), metrics(donor)
    if b is None or d is None or amount <= 0: return None
    cost = (fees(amount, 'SELL') + fees(amount, 'BUY')) / amount * 100 + .86
    score_gap = rules.finite(buyer.get('score'), 0) - rules.finite(donor.get('score'), 0)
    if (score_gap < PARAMETERS['scoreGap'] or b[0]-d[0] < cost+PARAMETERS['spaceMarginPct']
            or b[1] < PARAMETERS['minRewardRisk'] or b[1]-d[1] < PARAMETERS['rewardRiskGap']): return None
    return dict(scoreGap=score_gap, buyerSpacePct=b[0], donorSpacePct=d[0],
                costAllowancePct=cost, buyerRewardRisk=b[1], donorRewardRisk=d[1],
                noteZh='空间依据当前价格至近20日高点，不是预测收益率')


def run(engine, state, ledger, targets, radar, prices):
    base, execution = engine.base, engine.execution
    obj = engine.metadata(state); now = base.now_cn(); today = now.date().isoformat()
    book = obj.setdefault('rotation49', {'activatedAt': base.iso(), 'plans': [], 'statusZh': '等待可比较机会'})
    if engine.CONTROL_MODE == 'FIXED_HOLD': return []
    risk = engine.risk_control(state, prices)
    nav, mv = base.portfolio_nav(state, prices)
    by_code = {t['code']: t for t in targets}
    plan = active(obj)
    if plan:
        plan = next((p for p in book['plans'] if p['id'] == plan['id']), plan)
        book['active'] = plan
    def cancel(reason, status='CANCELLED'):
        plan.update(status=status, reasonZh=reason, updatedAt=base.iso())
        book['statusZh'] = reason
    def evidence(t):
        # Missing donor data must never be interpreted as inferior quality.
        stock = engine.signal_stock(state, t['code'], radar)
        y = stock.get('yunai') or {}; p = rules.finite(t.get('referencePrice'), 0)
        sector = next((s for s in radar.get('mainlines', []) if s.get('name') == t['sector']), {})
        return (engine.own_quote_ok(t['code']) and y.get('quoteOk') and rules.fresh(y.get('quoteTime'), now)
                and rules.finite(y.get('price'), 0) > 0 and p > 0 and abs(p/y['price']-1) <= .003
                and stock.get('rankComplete') is True and rules.finite(sector.get('return5Pct')) is not None
                and len(rules.sector_evidence(stock, sector, today, now)) >= 2)
    def allowed_buyer(t):
        return (t and not t.get('rejections') and evidence(t)
                and obj.get('confirmations', {}).get(t['code'], {}).get('count', 0) >= 3
                and t['code'] not in obj.get('pendingExits', {}))
    if plan and (plan['date'] != today or now > rules.stamp(plan['expiresAt'])):
        cancel('换仓计划到期；已成交保留，剩余资金等待重新评估', 'EXPIRED'); return []
    if not risk.get('allowNew') or risk.get('forceReduction') or obj.get('pendingExits'):
        if plan: cancel('策略退出或组合风控优先，取消择优换仓余量')
        book['statusZh'] = '先处理退出和组合风控，不用换仓绕过风险限制'; return []
    if not rules.normal_window(now):
        book['statusZh'] = '等待普通交易窗口'; return []
    # Replacement does not excuse existing excessive exposure.
    if mv > nav * risk['cap'] + 1:
        if plan: cancel('当前总仓位超出风险上限，先按主策略降仓')
        book['statusZh'] = '总仓位超过风险上限，优先降仓'; return []
    if plan is None:
        if sum(p['date'] == today for p in book['plans']) >= PARAMETERS['maxPlansPerDay']:
            book['statusZh'] = '达到当日择优换仓计划上限'; return []
        choices = []
        for buyer in targets:
            if buyer['code'] in state.get('positions', {}) or not allowed_buyer(buyer): continue
            need = min(nav * buyer['targetWeight'], nav * PARAMETERS['maxNavFraction'])
            if state['cash'] >= need: continue  # Normal entry path already handles sufficient cash.
            for code, pos in state.get('positions', {}).items():
                donor = by_code.get(code)
                # Same current scoring universe; off-radar absence is not a sell signal.
                if not donor or not evidence(donor) or pos.get('completeObservedDays', 0) < 2: continue
                amount = min(need-state['cash'], pos['qty']*prices[code]*PARAMETERS['maxDonorFraction'],
                             engine.turnover_room(state, ledger, nav)/2.02)
                comparison = edge(buyer, donor, amount, base.fees)
                if not comparison or amount < max(prices[code], buyer['referencePrice'])*100*1.02: continue
                choices.append((comparison['scoreGap'], comparison['buyerSpacePct']-comparison['donorSpacePct'],
                                buyer, donor, amount, comparison))
        if not choices:
            book.pop('proposal', None)
            book['statusZh'] = '无证据完整且优势覆盖成本的换仓组合'; return []
        _, _, buyer, donor, amount, comparison = max(choices, key=lambda x:(x[0],x[1]))
        pair = donor['code'] + '>' + buyer['code']
        proposal = book.setdefault('proposal', {})
        at = min(rules.stamp((engine.CONTEXT['quotes'][c]).get('quoteTimestamp') or engine.CONTEXT['quotes'][c].get('quoteTime')) for c in (buyer['code'],donor['code']))
        before = rules.stamp(proposal.get('at'))
        if proposal.get('pair') != pair or (before and (at-before).total_seconds() > 900):
            proposal.clear(); before = None
        if not before or (at-before).total_seconds() >= 180:
            proposal.update(pair=pair, at=at.isoformat(), count=proposal.get('count',0)+1, comparison=comparison)
        if proposal.get('count',0) < PARAMETERS['pairConfirmations']:
            book['statusZh'] = '新旧机会优势等待3次间隔至少3分钟的确认'; return []
        qty = int(amount/prices[donor['code']]/100)*100
        plan = dict(id='ROT49-'+base.iso()+'-'+donor['code']+'-'+buyer['code'], date=today,
                    createdAt=base.iso(), expiresAt=(now+timedelta(minutes=PARAMETERS['maxAgeMinutes'])).isoformat(),
                    sellCode=donor['code'], buyCode=buyer['code'], sellName=donor['name'], buyName=buyer['name'],
                    requestedSellQty=qty, remainingSellQty=qty, soldQty=0, boughtQty=0, proceeds=0., spent=0.,
                    cashAtCreation=float(state['cash']), budget=amount+float(state['cash']),
                    targetWeight=buyer['targetWeight'], maxBuyPrice=buyer['referencePrice']*(1+PARAMETERS['maxPriceRisePct']/100),
                    status='PENDING', comparison=comparison, sellDecisionIds=[], buyDecisionIds=[],
                    reasonZh='新机会评分、阻力位空间与风险收益比较通过；先卖后买')
        book['plans'].append(plan); book['active'] = plan
    buyer, donor = by_code.get(plan['buyCode']), by_code.get(plan['sellCode'])
    if (not allowed_buyer(buyer) or not donor or not evidence(donor)
            or buyer['referencePrice'] > plan['maxBuyPrice']
            or not edge(buyer, donor, max(plan['budget'], 1), base.fees)):
        cancel('新旧机会比较或买入条件已失效，停止余量；已卖出资金保留现金'); return []
    # Pending risk exits may have filled before this function and disappeared.
    if any(x.get('code') in (plan['sellCode'],plan['buyCode']) and x.get('timestamp','') >= plan['createdAt']
           and x.get('rotationId') != plan['id'] for x in ledger):
        cancel('主策略已有独立成交，取消原换仓余量并重新评估'); return []
    pos = state.get('positions', {}).get(plan['sellCode'])
    if not pos:
        cancel('原持仓已退出，不继续旧换仓计划'); return []
    # Prospective sector/group limits: cash freed in another sector cannot bypass concentration caps.
    def room(release=0.):
        n, market = base.portfolio_nav(state, prices)
        cw, sw, _ = base.current_weights(state, prices)
        group = buyer.get('correlationGroup', 'UNVERIFIED_GROUP')
        gv = sum(p['qty']*prices.get(c,p.get('lastPrice',p['avgCost'])) for c,p in state['positions'].items()
                 if p.get('correlationGroup','UNVERIFIED_GROUP') == group)
        return min(max(0,buyer['targetWeight']*n-cw.get(buyer['code'],0)*n),
                   max(0,risk['cap']*n-market+release),
                   max(0,.25*n-sw.get(buyer['sector'],0)*n+(release if pos['sector']==buyer['sector'] else 0)),
                   max(0,.35*n-gv+(release if pos.get('correlationGroup','UNVERIFIED_GROUP')==group else 0)),
                   max(0,plan['budget']-plan['spent']), engine.turnover_room(state,ledger,n)/2.02)
    price = buyer['referencePrice']; sell_price = prices[plan['sellCode']]
    sale_qty = min(plan['remainingSellQty'],execution.sellable_qty(pos,today))
    prospective = room(sale_qty*sell_price)
    requested = int(min(prospective, state['cash']+sale_qty*sell_price*.99)/(price*1.01)/100)*100
    if requested < 100:
        plan['status'] = 'WAIT_T_PLUS_ONE' if sale_qty <= 0 and plan['remainingSellQty'] else 'WAIT_RISK_ROOM'
        book['statusZh'] = '旧票受T+1约束，等待可卖数量' if plan['status']=='WAIT_T_PLUS_ONE' else '现金、仓位、集中度或换手额度不足'; return []
    check = base.fund.plan_execution(deepcopy(state), side='BUY', code=buyer['code'], name=buyer['name'],
                requested_qty=requested, reference_price=price, market=base.EXECUTION_MARKET.get(buyer['code']) or {}, day=today)
    if not check.get('allowed'):
        plan['status']='WAIT_BUY_CAPACITY'; book['statusZh']='新票当前无法成交，不先卖旧票'; return []
    fills=[]
    # Sell only enough for the currently executable buy, allowing actual fees and spread.
    gap=max(0,check['filledQty']*check['executionPrice']*1.01-state['cash'])
    if gap > 0 and sale_qty > 0:
        import math
        sale_qty=min(sale_qty,math.ceil(gap/(sell_price*.99)/100)*100)
        sold=execution.reduce_or_sell(state,ledger,pos,sale_qty,sell_price,0,'择优换仓：释放实际买入资金')
        if sold:
            engine.cancel_t_buybacks(obj,plan['sellCode'],'择优换仓卖出优先，终止旧T回补')
            engine.annotate(state,sold,'ROTATION_SELL',plan['comparison'])
            sold['rotationId']=plan['id'];plan['soldQty']+=sold['qty'];plan['remainingSellQty']-=sold['qty']
            plan['proceeds']+=sold['amount']-sold['fee'];plan['sellDecisionIds'].append(sold['decisionId']);fills.append(sold)
        else:
            plan['status']='WAIT_SELL_CAPACITY';book['statusZh']='旧票未成交，不预支卖出资金';return []
    qty=int(min(room(),state['cash'],max(0,plan['cashAtCreation']+plan['proceeds']-plan['spent']))/(price*1.01)/100)*100
    if qty >= 100:
        row=execution.add_or_buy(state,ledger,buyer,qty,prices,'择优换仓：按实际现金买入更优机会')
        if row:
            engine.cancel_t_buybacks(obj,plan['buyCode'],'主策略换仓买入优先')
            engine.annotate(state,row,'ROTATION_BUY',plan['comparison']);row['rotationId']=plan['id']
            plan['boughtQty']+=row['qty'];plan['spent']+=row['amount']+row['fee'];plan['buyDecisionIds'].append(row['decisionId']);fills.append(row)
            bought=state['positions'][buyer['code']]
            bought.update(coreTargetWeight45=buyer['targetWeight'],lastCoreBuyPrice=price,
                          correlationGroup=buyer.get('correlationGroup','UNVERIFIED_GROUP'),riskBasis=bought['avgCost'])
    plan['status']='DONE' if plan['remainingSellQty'] <= 0 and min(room(),state['cash'],plan['cashAtCreation']+plan['proceeds']-plan['spent']) < price*100*1.01 else 'PARTIAL_WAIT'
    plan['updatedAt']=base.iso(); book['statusZh']='换仓完成' if plan['status']=='DONE' else '换仓部分成交，余量等待重新核验'
    return fills


def expire_snapshot(obj, now):
    plan=active(obj)
    if plan and (plan['date'] != now.date().isoformat() or now > rules.stamp(plan['expiresAt'])):
        book=obj['rotation49']
        for row in [plan]+book.get('plans',[]):
            if row['id']==plan['id']:
                row.update(status='EXPIRED',reasonZh='换仓计划已到期，停止未成交余量；保留真实成交与现金',updatedAt=now.isoformat())
        book['statusZh']='换仓计划已到期，等待新机会重新确认'
