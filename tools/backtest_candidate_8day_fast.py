#!/usr/bin/env python3
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pytdx.hq import TdxHq_API
import backtest_candidate_8day as base

SERVERS=[
 ('sztdx.gtjas.com',7709),('shtdx.gtjas.com',7709),('jstdx.gtjas.com',7709),
 ('hq.cjis.cn',7709),('hq1.daton.com.cn',7709),('119.147.212.81',7709),
 ('101.227.73.20',7709),('114.80.80.222',7709),('180.153.18.170',7709)
]

def choose_server():
    errors=[]
    for host,port in SERVERS:
        api=TdxHq_API(heartbeat=False,auto_retry=True,raise_exception=False)
        try:
            ok=api.connect(host,port,time_out=1.5)
            test=api.get_security_bars(0,0,'000001',0,2) if ok else None
            api.disconnect()
            if test:
                print('TDX_SERVER',host,port,'OK')
                return host,port
            errors.append(f'{host}:empty')
        except Exception as e:
            try: api.disconnect()
            except: pass
            errors.append(f'{host}:{type(e).__name__}')
    raise RuntimeError('no TDX server: '+';'.join(errors))

def fetch_chunk(codes,server):
    host,port=server; out={}; errs={}
    api=TdxHq_API(heartbeat=False,auto_retry=True,raise_exception=False)
    if not api.connect(host,port,time_out=2):
        return {},{c:'connect failed' for c in codes}
    for code in codes:
        try:
            market=1 if code.startswith('6') else 0
            rows=[]
            for start in (0,800):
                part=api.get_security_bars(0,market,code,start,800) or []
                rows.extend(part)
            parsed=base.parse_bars(rows)
            if parsed: out[code]=parsed
            else: errs[code]='empty bars'
        except Exception as e:
            errs[code]=type(e).__name__+':'+str(e)[:120]
            try:
                api.disconnect(); api=TdxHq_API(heartbeat=False,auto_retry=True,raise_exception=False); api.connect(host,port,time_out=2)
            except: pass
    try: api.disconnect()
    except: pass
    return out,errs

def load_prices(codes):
    server=choose_server(); codes=sorted(codes); workers=6
    chunks=[codes[i::workers] for i in range(workers)]
    prices={}; errs={}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        fs=[ex.submit(fetch_chunk,ch,server) for ch in chunks if ch]
        for f in as_completed(fs):
            p,e=f.result(); prices.update(p); errs.update(e)
    return prices,errs,server

def main():
    cands,missing=base.candidate_rows(); codes={x['code'] for x in cands}
    prices,errs,server=load_prices(codes)
    coverage=[{'date':x['date'],'code':x['code'],'name':x['name'],'reason':'missing buy-day 5m data'} for x in cands if not (prices.get(x['code']) or {}).get(x['date'],{}).get('open5_vwap')]
    fallbacks=[{'date':d,'code':c,'method':p.get('method')} for c,ds in prices.items() for d,p in ds.items() if p.get('method')!='tdx_amount_volume']
    res={'as_of':'2026-10-07','latest_market_date':'2026-09-30','methodology':{'buy':'first 5-minute VWAP = amount/volume from TDX 5m bar, unadjusted actual price','sell':'8 subsequent trading days later first 5-minute VWAP; if suspended, first later tradable open5 VWAP','mark_to_market':'daily close from final 5-minute bar','fees':'0','capital':'8 rotating sleeves, initial NAV=1.0','rule1':'equal weight within daily sleeve','rule2':'weight proportional to score within daily sleeve'},'candidate_count':len(cands),'unique_codes':len(codes),'missing_history_days':missing,'price_errors':errs,'coverage_issues':coverage,'vwap_fallbacks':fallbacks,'tdx_server':f'{server[0]}:{server[1]}','rule1':base.simulate(cands,prices,'equal'),'rule2':base.simulate(cands,prices,'score')}
    base.OUT.parent.mkdir(parents=True,exist_ok=True); base.OUT.write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'output':str(base.OUT.relative_to(base.ROOT)),'server':res['tdx_server'],'candidates':len(cands),'codes':len(codes),'price_errors':len(errs),'coverage':len(coverage),'fallbacks':len(fallbacks),'rule1':res['rule1']['summary'],'rule2':res['rule2']['summary']},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
