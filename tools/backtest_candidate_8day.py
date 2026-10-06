#!/usr/bin/env python3
import json
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pytdx.hq import TdxHq_API
try:
    from pytdx.config.hosts import hq_hosts
except Exception:
    hq_hosts=[]

ROOT=Path(__file__).resolve().parents[1]
START='2026-08-19'; END='2026-09-30'
OUT=ROOT/'backtests'/'candidate_8day_backtest_20261007.json'
TRADING_DAYS=['2026-08-19','2026-08-20','2026-08-21','2026-08-24','2026-08-25','2026-08-26','2026-08-27','2026-08-28','2026-08-31','2026-09-01','2026-09-02','2026-09-03','2026-09-04','2026-09-07','2026-09-08','2026-09-09','2026-09-10','2026-09-11','2026-09-14','2026-09-15','2026-09-16','2026-09-17','2026-09-18','2026-09-21','2026-09-22','2026-09-23','2026-09-24','2026-09-28','2026-09-29','2026-09-30']

def candidate_rows():
    rows=[]; missing=[]
    for d in TRADING_DAYS:
        p=ROOT/'astock_trade'/'history'/f'{d}.json'
        if not p.exists(): missing.append(d); continue
        obj=json.loads(p.read_text(encoding='utf-8')); rank=0
        for src,key in [('official','officialPlans'),('expanded','setupCandidates')]:
            for x in obj.get(key,[]) or []:
                if src=='official' and x.get('action') not in ('买入候选','等待触发'): continue
                rank+=1; setup=x.get('setup') or {}
                rows.append({'date':d,'rank':rank,'source':src,'code':str(x.get('code','')).zfill(6),'name':x.get('name',''),'sector':x.get('sector',''),'action':x.get('action',''),'setup':setup.get('label',''),'score':float(setup.get('score') or 0)})
    return rows,missing

def server_list():
    out=[]
    for h in hq_hosts:
        try:
            if isinstance(h,(list,tuple)) and len(h)>=3: out.append((str(h[-2]),int(h[-1])))
            elif isinstance(h,dict): out.append((str(h.get('ip') or h.get('host')),int(h.get('port',7709))))
        except: pass
    # commonly available TDX quote servers; duplicates removed below
    out += [('119.147.212.81',7709),('101.227.73.20',7709),('114.80.80.222',7709),('180.153.18.170',7709),('202.108.253.130',7709)]
    seen=set(); ans=[]
    for x in out:
        if x not in seen and x[0] and x[0]!='None': seen.add(x); ans.append(x)
    return ans[:15]

def parse_bars(rows):
    byday=defaultdict(list)
    for b in rows:
        dt=str(b.get('datetime') or '')
        d=dt[:10]
        if not (START<=d<=END): continue
        try:
            o=float(b.get('open')); c=float(b.get('close')); h=float(b.get('high')); l=float(b.get('low'))
            vol=float(b.get('vol') if b.get('vol') is not None else b.get('volume'))
            amt=float(b.get('amount') or 0)
        except: continue
        byday[d].append({'ts':dt,'open':o,'close':c,'high':h,'low':l,'vol':vol,'amt':amt})
    parsed={}
    for d,bars in byday.items():
        bars=sorted(bars,key=lambda x:x['ts']); f=bars[0]; vwap=None; method='tdx_amount_volume'
        if f['vol']>0 and f['amt']>0:
            v1=f['amt']/f['vol']; v2=f['amt']/(f['vol']*100.0); lo,hi=f['low']*.97,f['high']*1.03
            if lo<=v1<=hi: vwap=v1
            elif lo<=v2<=hi: vwap=v2
        if not vwap:
            vwap=(f['open']+f['high']+f['low']+f['close'])/4; method='ohlc4_fallback'
        parsed[d]={'open5_vwap':vwap,'close':bars[-1]['close'],'first_bar':f['ts'],'bars':len(bars),'method':method}
    return parsed

def fetch_code(code):
    market=1 if code.startswith('6') else 0; errors=[]
    for ip,port in server_list():
        api=TdxHq_API(heartbeat=False,auto_retry=True,raise_exception=False)
        try:
            if not api.connect(ip,port):
                errors.append(f'{ip}:connect'); continue
            rows=[]
            for start in (0,800,1600):
                chunk=api.get_security_bars(0,market,code,start,800) or []
                rows.extend(chunk)
                if len(chunk)<800: break
            api.disconnect()
            p=parse_bars(rows)
            if p and any(d in p for d in TRADING_DAYS): return code,p,None,f'{ip}:{port}'
            errors.append(f'{ip}:empty')
        except Exception as e:
            try: api.disconnect()
            except: pass
            errors.append(f'{ip}:{type(e).__name__}')
    return code,{},';'.join(errors[-5:]),None

def load_prices(codes):
    prices={}; errs={}; servers={}
    with ThreadPoolExecutor(max_workers=12) as ex:
        fs=[ex.submit(fetch_code,c) for c in sorted(codes)]
        for f in as_completed(fs):
            c,p,e,s=f.result(); prices[c]=p
            if e: errs[c]=e
            if s: servers[c]=s
    return prices,errs,servers

def simulate(cands,prices,rule):
    byday=defaultdict(list)
    for x in cands: byday[x['date']].append(x)
    sleeves=[{'cash':1/8,'positions':[]} for _ in range(8)]; trades=[]; daily=[]
    for i,d in enumerate(TRADING_DAYS):
        # scheduled exits happen at the first 5-minute VWAP; suspended names remain held until tradable
        for s in sleeves:
            keep=[]
            for ti in s['positions']:
                t=trades[ti]
                if i>=t['scheduled_exit_index']:
                    px=(prices.get(t['code']) or {}).get(d,{}).get('open5_vwap')
                    if px:
                        proceeds=t['shares']*px; s['cash']+=proceeds
                        t.update({'exit_date':d,'exit_price':px,'exit_value':proceeds,'status':'realized','trade_return':px/t['buy_price']-1})
                    else: keep.append(ti)
                else: keep.append(ti)
            s['positions']=keep
        # rotate one of eight capital sleeves into today's candidates
        s=sleeves[i%8]; today=byday.get(d,[])
        if today and not s['positions'] and s['cash']>1e-12:
            avail=[]
            for x in today:
                px=(prices.get(x['code']) or {}).get(d,{}).get('open5_vwap')
                if px and px>0: avail.append((x,px))
            if avail:
                raw=[1.0]*len(avail) if rule=='equal' else [max(x['score'],.0001) for x,_ in avail]
                den=sum(raw); bucket=s['cash']; s['cash']=0
                for (x,px),rw in zip(avail,raw):
                    alloc=bucket*rw/den; sched=i+8
                    trades.append({**x,'sleeve':i%8+1,'buy_date':d,'buy_price':px,'allocation':alloc,'day_weight':rw/den,'shares':alloc/px,'scheduled_exit_date':TRADING_DAYS[sched] if sched<len(TRADING_DAYS) else None,'scheduled_exit_index':sched,'exit_date':None,'exit_price':None,'exit_value':None,'status':'open','trade_return':None})
                    s['positions'].append(len(trades)-1)
        # end-of-day mark for NAV/drawdown
        nav=0; invested=0
        for s2 in sleeves:
            nav+=s2['cash']
            for ti in s2['positions']:
                t=trades[ti]; pdata=prices.get(t['code']) or {}; close=(pdata.get(d) or {}).get('close')
                if close is None:
                    close=t['buy_price']
                    for dd in reversed(TRADING_DAYS[:i+1]):
                        if (pdata.get(dd) or {}).get('close') is not None: close=pdata[dd]['close']; break
                val=t['shares']*close; nav+=val; invested+=val; t['last_mark_date']=d; t['last_mark_price']=close; t['last_mark_value']=val
        daily.append({'date':d,'nav':nav,'invested':invested,'cash':nav-invested})
    peak=1; maxdd=0; prev=1
    for r in daily:
        r['daily_return']=r['nav']/prev-1; prev=r['nav']; peak=max(peak,r['nav']); r['drawdown']=r['nav']/peak-1; maxdd=min(maxdd,r['drawdown'])
    for t in trades:
        if t['status']=='open': t['current_value']=t.get('last_mark_value',t['allocation']); t['trade_return']=t['current_value']/t['allocation']-1
        else: t['current_value']=t['exit_value']
    realized=[t for t in trades if t['status']=='realized']; opens=[t for t in trades if t['status']=='open']; final=daily[-1]['nav']
    return {'summary':{'end_nav':final,'cumulative_return':final-1,'max_drawdown':maxdd,'realized_trades':len(realized),'open_trades':len(opens),'realized_win_rate':sum(1 for t in realized if t['trade_return']>0)/len(realized) if realized else None,'realized_pnl':sum(t['exit_value']-t['allocation'] for t in realized),'open_unrealized_pnl':sum(t['current_value']-t['allocation'] for t in opens)},'daily':daily,'trades':trades}

def main():
    cands,missing=candidate_rows(); codes={x['code'] for x in cands}; prices,errs,servers=load_prices(codes)
    coverage=[{'date':x['date'],'code':x['code'],'name':x['name'],'reason':'missing buy-day 5m data'} for x in cands if not (prices.get(x['code']) or {}).get(x['date'],{}).get('open5_vwap')]
    fallbacks=[{'date':d,'code':c,'method':p.get('method')} for c,ds in prices.items() for d,p in ds.items() if p.get('method')!='tdx_amount_volume']
    res={'as_of':'2026-10-07','latest_market_date':'2026-09-30','methodology':{'buy':'first 5-minute VWAP = amount/volume from TDX 5m bar, unadjusted actual price','sell':'8 subsequent trading days later first 5-minute VWAP; if suspended, first later tradable open5 VWAP','mark_to_market':'daily close from final 5-minute bar','fees':'0','capital':'8 rotating sleeves, initial NAV=1.0','rule1':'equal weight within daily sleeve','rule2':'weight proportional to score within daily sleeve'},'candidate_count':len(cands),'unique_codes':len(codes),'missing_history_days':missing,'price_errors':errs,'coverage_issues':coverage,'vwap_fallbacks':fallbacks,'tdx_servers_used':servers,'rule1':simulate(cands,prices,'equal'),'rule2':simulate(cands,prices,'score')}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'output':str(OUT.relative_to(ROOT)),'candidates':len(cands),'codes':len(codes),'price_errors':len(errs),'coverage':len(coverage),'fallbacks':len(fallbacks),'rule1':res['rule1']['summary'],'rule2':res['rule2']['summary']},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
