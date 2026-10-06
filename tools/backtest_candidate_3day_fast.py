#!/usr/bin/env python3
import json
from collections import defaultdict
import backtest_candidate_8day as base
import backtest_candidate_8day_fast as fast

HOLD_DAYS=3
OUT=base.ROOT/'backtests'/'candidate_3day_backtest_20261007.json'


def simulate(cands,prices,rule):
    byday=defaultdict(list)
    for x in cands:
        byday[x['date']].append(x)
    sleeves=[{'cash':1/8,'positions':[]} for _ in range(8)]
    trades=[]; daily=[]; pending=[]

    for i,d in enumerate(base.TRADING_DAYS):
        # Exit at the first 5-minute VWAP HOLD_DAYS trading sessions after entry.
        for s in sleeves:
            keep=[]
            for ti in s['positions']:
                t=trades[ti]
                if i>=t['scheduled_exit_index']:
                    px=(prices.get(t['code']) or {}).get(d,{}).get('open5_vwap')
                    if px:
                        proceeds=t['shares']*px
                        s['cash']+=proceeds
                        t.update({'exit_date':d,'exit_price':px,'exit_value':proceeds,'status':'realized','trade_return':px/t['buy_price']-1})
                    else:
                        keep.append(ti)
                else:
                    keep.append(ti)
            s['positions']=keep

        # Signal generated on D is bought on D+1 at first 5-minute VWAP.
        signal_date=base.TRADING_DAYS[i-1] if i>0 else None
        today=byday.get(signal_date,[]) if signal_date else []
        s=sleeves[i%8]
        if today and s['cash']>1e-12:
            avail=[]
            for x in today:
                px=(prices.get(x['code']) or {}).get(d,{}).get('open5_vwap')
                if px and px>0:
                    avail.append((x,px))
            if avail:
                raw=[1.0]*len(avail) if rule=='equal' else [max(x['score'],.0001) for x,_ in avail]
                den=sum(raw); bucket=s['cash']; s['cash']=0
                for (x,px),rw in zip(avail,raw):
                    alloc=bucket*rw/den
                    sched=i+HOLD_DAYS
                    trades.append({**x,'signal_date':x['date'],'sleeve':i%8+1,'buy_date':d,'buy_price':px,'allocation':alloc,'day_weight':rw/den,'shares':alloc/px,'scheduled_exit_date':base.TRADING_DAYS[sched] if sched<len(base.TRADING_DAYS) else None,'scheduled_exit_index':sched,'exit_date':None,'exit_price':None,'exit_value':None,'status':'open','trade_return':None})
                    s['positions'].append(len(trades)-1)

        nav=0; invested=0
        for s2 in sleeves:
            nav+=s2['cash']
            for ti in s2['positions']:
                t=trades[ti]
                pdata=prices.get(t['code']) or {}
                close=(pdata.get(d) or {}).get('close')
                if close is None:
                    close=t['buy_price']
                    for dd in reversed(base.TRADING_DAYS[:i+1]):
                        if (pdata.get(dd) or {}).get('close') is not None:
                            close=pdata[dd]['close']; break
                val=t['shares']*close
                nav+=val; invested+=val
                t['last_mark_date']=d; t['last_mark_price']=close; t['last_mark_value']=val
        daily.append({'date':d,'nav':nav,'invested':invested,'cash':nav-invested})

    for x in byday.get(base.TRADING_DAYS[-1],[]):
        pending.append({**x,'signal_date':x['date'],'buy_date':None,'status':'pending_next_session'})

    peak=1; maxdd=0; prev=1
    for r in daily:
        r['daily_return']=r['nav']/prev-1
        prev=r['nav']; peak=max(peak,r['nav'])
        r['drawdown']=r['nav']/peak-1
        maxdd=min(maxdd,r['drawdown'])
    for t in trades:
        if t['status']=='open':
            t['current_value']=t.get('last_mark_value',t['allocation'])
            t['trade_return']=t['current_value']/t['allocation']-1
        else:
            t['current_value']=t['exit_value']
    realized=[t for t in trades if t['status']=='realized']
    opens=[t for t in trades if t['status']=='open']
    final=daily[-1]['nav']
    return {'summary':{
        'end_nav':final,'cumulative_return':final-1,'max_drawdown':maxdd,
        'realized_trades':len(realized),'open_trades':len(opens),'pending_entries':len(pending),
        'realized_win_rate':sum(1 for t in realized if t['trade_return']>0)/len(realized) if realized else None,
        'realized_pnl':sum(t['exit_value']-t['allocation'] for t in realized),
        'open_unrealized_pnl':sum(t['current_value']-t['allocation'] for t in opens)
    },'daily':daily,'trades':trades,'pending':pending}


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
        'as_of':'2026-10-07','latest_market_date':'2026-09-30','holding_days':HOLD_DAYS,
        'methodology':{
            'signal':'candidate list is generated near/after the signal-day close',
            'buy':'next trading session first 5-minute VWAP = amount/volume from TDX 5m bar, unadjusted actual price',
            'sell':'3 trading days after entry at first 5-minute VWAP; if suspended, first later tradable open5 VWAP',
            'partial':'positions not yet at the 3-day exit are marked to latest available market close',
            'mark_to_market':'daily close from final 5-minute bar','fees':'0',
            'capital':'8 rotating sleeves, initial NAV=1.0; each sleeve is reused on its own 8-session rotation',
            'rule1':'equal weight within each daily sleeve','rule2':'weight proportional to score within each daily sleeve'
        },
        'candidate_count':len(cands),'unique_codes':len(codes),'missing_history_days':missing,
        'price_errors':errs,'coverage_issues':coverage,'vwap_fallbacks':fallbacks,
        'tdx_server':f'{server[0]}:{server[1]}',
        'rule1':simulate(cands,prices,'equal'),'rule2':simulate(cands,prices,'score')
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'output':str(OUT.relative_to(base.ROOT)),'server':res['tdx_server'],'candidates':len(cands),'codes':len(codes),'price_errors':len(errs),'coverage':len(coverage),'fallbacks':len(fallbacks),'rule1':res['rule1']['summary'],'rule2':res['rule2']['summary']},ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
