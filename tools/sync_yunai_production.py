#!/usr/bin/env python3
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
import enrich_yunai_gateway as yg
import yunai_tail_overlay as yo

ROOT=Path(__file__).resolve().parents[1]
GW=ROOT/'astock_gateway'/'latest.json'
TAIL=ROOT/'astock_tail'/'latest.json'
SNAPS=ROOT/'astock_snapshots'/'index.json'
OUT=ROOT/'astock_gateway'/'yunai_live.json'

def codes_to_check(today):
    codes=[]
    if TAIL.exists():
        try:
            t=json.loads(TAIL.read_text(encoding='utf-8'))
            if t.get('date')==today: codes+=list((t.get('stocks') or {}).keys())
        except Exception: pass
    if not codes and SNAPS.exists():
        try:
            arr=json.loads(SNAPS.read_text(encoding='utf-8'))
            if arr:
                x=sorted(arr,key=lambda z:z.get('date',''))[-1]
                pools=x.get('pools') or {}
                for p in ('B4','B3','B0'): codes+=(pools.get(p) or [])
        except Exception: pass
    return list(dict.fromkeys(str(c) for c in codes if c))[:40]

def shape(p):
    if isinstance(p,dict):
        vals={str(k):type(v).__name__ for k,v in list(p.items())[:10]}
        return {'type':'dict','keys':list(p.keys())[:10],'valueTypes':vals}
    if isinstance(p,list): return {'type':'list','count':len(p),'firstType':type(p[0]).__name__ if p else None}
    return {'type':type(p).__name__,'preview':str(p)[:120]}

def main():
    now=datetime.now(yg.CN); today=now.strftime('%Y-%m-%d')
    status_ok=False; status_summary={}
    try:
        st,_,p=yg.fetch(yg.MARKET_STATUS_PATH,{'market':'CN','lang':'zh_CN'},timeout=12)
        status_ok=200<=st<300
        status_summary={'httpStatus':st,'type':type(p).__name__,'count':len(p) if isinstance(p,list) else None}
    except Exception as e:
        status_summary={'error':e.__class__.__name__}
    codes=codes_to_check(today)
    overlay={}
    try:
        if codes: overlay=yo.fetch_stock_overlay(codes)
    except Exception as e:
        overlay={'_error':e.__class__.__name__}
    diagnostic={}
    for code in ['000001']+([codes[0]] if codes else []):
        try:
            st,_,p=yo.post(yo.PREFIX+'/real-time-quotes',{'symbols':[code]})
            diagnostic[code]={'httpStatus':st,'shape':shape(p)}
        except Exception as e:
            diagnostic[code]={'error':e.__class__.__name__}
    quote_ok=sum(1 for c in codes if (overlay.get(c) or {}).get('quoteOk'))
    cap_ok=sum(1 for c in codes if (overlay.get(c) or {}).get('capitalOk'))
    live={
        'checkedAt':now.isoformat(timespec='seconds'),'provider':'Yunai Quant API','connected':status_ok,
        'marketStatus':status_summary,'checkedSymbols':codes,'quoteAvailable':quote_ok,'capitalResponseAvailable':cap_ok,
        'stocks':{c:overlay.get(c) for c in codes if overlay.get(c)},'diagnostic':diagnostic,
        'roles':{'realTimeQuotes':'第二实时行情源','capitalDistribution':'独立大单资金分布，不等同东方财富主力净流入','barsRange':'已验证可用，按需用于历史K线/RS校验'},
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(live,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if GW.exists():
        g=json.loads(GW.read_text(encoding='utf-8'))
        g['yunaiProduction']={k:live[k] for k in ('checkedAt','provider','connected','marketStatus','checkedSymbols','quoteAvailable','capitalResponseAvailable','roles')}
        src=list(g.get('dataSources') or [])
        if status_ok and 'Yunai Quant API' not in src: src.insert(0,'Yunai Quant API')
        g['dataSources']=src
        GW.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'yunaiProduction':{'connected':status_ok,'symbols':len(codes),'quoteAvailable':quote_ok,'capitalResponseAvailable':cap_ok,'diagnostic':diagnostic}},ensure_ascii=False))

if __name__=='__main__': main()
