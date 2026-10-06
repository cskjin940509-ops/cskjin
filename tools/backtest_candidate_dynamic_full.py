#!/usr/bin/env python3
import json
from collections import defaultdict
import backtest_candidate_8day as base
import backtest_candidate_8day_fast as fast

OUT=base.ROOT/'backtests'/'candidate_dynamic_full_backtest_20261007.json'

SETUP_MULT={'趋势回踩':1.10,'突破回踩':1.00,'临界突破':0.70}

def hold_plan(label,score):
    if label=='趋势回踩':
        base_hold=5; max_hold=8
        if score>=90: base_hold=7
        elif score>=85: base_hold=6
    elif label=='突破回踩':
        base_hold=3; max_hold=6
        if score>=90: base_hold=5
        elif score>=85: base_hold=4
    elif label=='临界突破':
        base_hold=2; max_hold=4
        if score>=85: base_hold=3
    else:
        base_hold=3; max_hold=5
        if score>=85: base_hold=4
    return base_hold,max_hold

def closes_until(prices,code,end_i):
    ds=[]
    pdata=prices.get(code) or {}
    for d in base.TRADING_DAYS[:end_i+1]:
        v=(pdata.get(d) or {}).get('close')
        if v is not None: ds.append(float(v))
    return ds

def decision(pos,prices,i):
    # Decision at today's open uses only information through yesterday's close.
    age=i-pos['buy_index']
    if age<=0: return 'hold','same_day'
    hist=closes_until(prices,pos['code'],i-1)
    if not hist: return 'hold','no_history'
    prev=hist[-1]
    entry=pos['anchor_price']
    sma3=sum(hist[-3:])/min(3,len(hist))
    mom2=(hist[-1]/hist[-3]-1) if len(hist)>=3 and hist[-3]>0 else 0.0

    # Hard thesis failure: 5% loss from anchor, or persistent weak close after two sessions.
    if prev <= entry*0.95:
        return 'exit','hard_stop_5pct'
    if age>=2 and prev < entry and prev < sma3 and mom2<=0:
        return 'exit','setup_failed'

    if age < pos['base_hold']:
        return 'hold','within_base_hold'

    strong = (prev > entry*1.01 and prev >= sma3 and mom2>0)
    if strong and age < pos['max_hold']:
        return 'hold','trend_extension'
    return 'exit','planned_or_momentum_exit'

def factor_score(pos,prices,i):
    # Non-linear score + setup quality + state multiplier, all known before today's open.
    s=max(float(pos.get('score') or 0)-70.0,1.0)
    q=(s*s)*SETUP_MULT.get(pos.get('setup'),0.90)
    hist=closes_until(prices,pos['code'],i-1)
    if hist and pos.get('anchor_price'):
        prev=hist[-1]; entry=pos['anchor_price']; sma3=sum(hist[-3:])/min(3,len(hist))
        if prev>entry and prev>=sma3: q*=1.15
        elif prev<entry and prev<sma3: q*=0.80
    return max(q,1e-9)

def simulate(cands,prices,mode):
    byday=defaultdict(list)
    for x in cands: byday[x['date']].append(x)

    cash=1.0
    positions={}
    daily=[]; exits=[]; pending=[]
    total_turnover=0.0; exposure_sum=0.0; max_single_weight=0.0; position_days=0

    for i,d in enumerate(base.TRADING_DAYS):
        pdata_today={c:(prices.get(c) or {}).get(d,{}) for c in set(positions)|{x['code'] for x in byday.get(base.TRADING_DAYS[i-1],[]) if i>0}}

        # Portfolio value at today's executable open-5m prices before trading.
        nav_open=cash
        for code,p in positions.items():
            px=(prices.get(code) or {}).get(d,{}).get('open5_vwap')
            if px is None: px=p.get('last_close',p['anchor_price'])
            nav_open += p['shares']*px

        # Decide which existing theses survive today's open.
        keep={}
        for code,p in positions.items():
            act,reason=decision(p,prices,i)
            px=(prices.get(code) or {}).get(d,{}).get('open5_vwap')
            if px is None: px=p.get('last_close',p['anchor_price'])
            if act=='exit':
                exits.append({
                    'code':code,'name':p['name'],'setup':p['setup'],'score':p['score'],
                    'signal_date':p['signal_date'],'buy_date':p['buy_date'],'exit_date':d,
                    'entry_anchor':p['anchor_price'],'exit_price':px,'holding_sessions':i-p['buy_index'],
                    'reason':reason,'thesis_return':px/p['anchor_price']-1
                })
            else:
                keep[code]=p

        # Add prior-day signals; a repeated signal refreshes thesis metadata at today's open.
        signal_date=base.TRADING_DAYS[i-1] if i>0 else None
        new_today=byday.get(signal_date,[]) if signal_date else []
        for x in new_today:
            code=x['code']; px=(prices.get(code) or {}).get(d,{}).get('open5_vwap')
            if not px or px<=0: continue
            bh,mh=hold_plan(x.get('setup',''),float(x.get('score') or 0))
            if code in keep:
                p=keep[code]
                # Refresh only when the new signal is at least as strong as the current thesis.
                if float(x.get('score') or 0) >= float(p.get('score') or 0):
                    p.update({**x,'signal_date':x['date'],'buy_date':d,'buy_index':i,'anchor_price':px,'base_hold':bh,'max_hold':mh})
            else:
                keep[code]={**x,'signal_date':x['date'],'buy_date':d,'buy_index':i,'anchor_price':px,
                            'base_hold':bh,'max_hold':mh,'shares':0.0,'last_close':px}

        # If there is at least one active thesis, rebalance the ENTIRE NAV at today's open-5m VWAP.
        targets=keep
        old_values={}
        for code,p in positions.items():
            px=(prices.get(code) or {}).get(d,{}).get('open5_vwap')
            if px is None: px=p.get('last_close',p['anchor_price'])
            old_values[code]=p['shares']*px

        if targets:
            if mode=='equal':
                raw={c:1.0 for c in targets}
            else:
                raw={c:factor_score(p,prices,i) for c,p in targets.items()}
            den=sum(raw.values())
            new_positions={}
            day_turn=0.0
            for code,p in targets.items():
                px=(prices.get(code) or {}).get(d,{}).get('open5_vwap')
                if not px or px<=0: continue
                w=raw[code]/den
                target_val=nav_open*w
                old_val=old_values.get(code,0.0)
                day_turn += abs(target_val-old_val)
                p['shares']=target_val/px
                p['target_weight']=w
                max_single_weight=max(max_single_weight,w)
                new_positions[code]=p
            # Count sales of names not in target set.
            for code,val in old_values.items():
                if code not in new_positions: day_turn += val
            total_turnover += day_turn/max(nav_open,1e-12)
            positions=new_positions
            cash=0.0
        else:
            total_turnover += sum(old_values.values())/max(nav_open,1e-12)
            positions={}
            cash=nav_open

        # Mark portfolio at end-of-day close.
        nav_close=cash; invested=0.0
        for code,p in positions.items():
            close=(prices.get(code) or {}).get(d,{}).get('close')
            if close is None: close=p.get('last_close',p['anchor_price'])
            p['last_close']=close
            val=p['shares']*close
            nav_close+=val; invested+=val
        exposure=invested/max(nav_close,1e-12)
        exposure_sum+=exposure; position_days+=1
        daily.append({'date':d,'nav':nav_close,'invested':invested,'cash':nav_close-invested,
                      'exposure':exposure,'positions':len(positions)})

    for x in byday.get(base.TRADING_DAYS[-1],[]):
        pending.append({**x,'signal_date':x['date'],'status':'pending_next_session'})

    peak=1.0; prev=1.0; maxdd=0.0
    for r in daily:
        r['daily_return']=r['nav']/prev-1; prev=r['nav']
        peak=max(peak,r['nav']); r['drawdown']=r['nav']/peak-1; maxdd=min(maxdd,r['drawdown'])
    win=sum(1 for e in exits if e['thesis_return']>0)/len(exits) if exits else None
    return {
        'summary':{
            'end_nav':daily[-1]['nav'],'cumulative_return':daily[-1]['nav']-1,'max_drawdown':maxdd,
            'exit_events':len(exits),'exit_win_rate':win,'open_positions':len(positions),
            'pending_entries':len(pending),'avg_exposure':exposure_sum/max(position_days,1),
            'avg_daily_turnover':total_turnover/max(position_days,1),'max_single_weight':max_single_weight
        },
        'daily':daily,'exits':exits,'open_positions':list(positions.values()),'pending':pending
    }

def main():
    cands,missing=base.candidate_rows(); codes={x['code'] for x in cands}
    prices,errs,server=fast.load_prices(codes)
    coverage=[]
    for x in cands:
        bd=base.next_session(x['date'])
        if bd and not (prices.get(x['code']) or {}).get(bd,{}).get('open5_vwap'):
            coverage.append({'signal_date':x['date'],'buy_date':bd,'code':x['code'],'name':x['name'],'reason':'missing next-session 5m data'})
    fallbacks=[{'date':d,'code':c,'method':p.get('method')} for c,ds in prices.items() for d,p in ds.items() if p.get('method')!='tdx_amount_volume']
    res={
        'as_of':'2026-10-07','latest_market_date':'2026-09-30',
        'methodology':{
            'signal':'candidate list generated near/after signal-day close',
            'execution':'all buys, exits and rebalances use next-session first 5-minute VWAP',
            'holding':'setup/score initial horizon plus prior-close trend failure or extension; all decisions lagged one session',
            'trend_pullback':'base 5d; score>=85 ->6d; score>=90 ->7d; max 8d',
            'breakout_pullback':'base 3d; score>=85 ->4d; score>=90 ->5d; max 6d',
            'critical_breakout':'base 2d; score>=85 ->3d; max 4d',
            'early_exit':'prior close <=95% of anchor OR age>=2 and prior close below anchor, below 3-close average, non-positive 2-session momentum',
            'extension':'at/after base horizon, continue one session at a time only if prior close >101% anchor, >=3-close average, positive 2-session momentum',
            'portfolio':'if any active theses exist, rebalance full NAV at open-5m VWAP; no fixed 8 sleeves',
            'equal':'equal weight across active theses',
            'factor':'(score-70)^2 * setup multiplier * prior-close trend-state multiplier',
            'fees':'0'
        },
        'candidate_count':len(cands),'unique_codes':len(codes),'missing_history_days':missing,
        'price_errors':errs,'coverage_issues':coverage,'vwap_fallbacks':fallbacks,
        'tdx_server':f'{server[0]}:{server[1]}',
        'dynamic_equal':simulate(cands,prices,'equal'),
        'dynamic_factor':simulate(cands,prices,'factor')
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({
        'output':str(OUT.relative_to(base.ROOT)),'server':res['tdx_server'],'candidates':len(cands),'codes':len(codes),
        'price_errors':len(errs),'coverage':len(coverage),'fallbacks':len(fallbacks),
        'dynamic_equal':res['dynamic_equal']['summary'],'dynamic_factor':res['dynamic_factor']['summary']
    },ensure_ascii=False,indent=2))

if __name__=='__main__': main()
