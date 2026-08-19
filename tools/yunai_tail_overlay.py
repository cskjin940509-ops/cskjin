#!/usr/bin/env python3
from __future__ import annotations
import math
from datetime import datetime, timedelta
import enrich_yunai_gateway as yg

PREFIX='/quant-market/api/v1/quantitative/quotes'

def finite(v):
    try:
        x=float(v); return x if math.isfinite(x) else None
    except Exception: return None

def symbol_map(p):
    if not isinstance(p,dict): return {}
    d=p.get('data')
    if isinstance(d,dict): return d
    return {str(k):v for k,v in p.items() if isinstance(v,(dict,list))}

def scalar(o,names):
    if not isinstance(o,dict): return None
    for k in names:
        if k in o:
            v=finite(o.get(k))
            if v is not None: return v
    return None

def fetch_stock_overlay(codes):
    out={c:{'quoteOk':False,'capitalOk':False} for c in codes}
    for i in range(0,len(codes),20):
        batch=codes[i:i+20]
        try:
            st,_,p=yg.fetch(PREFIX+'/real-time-quotes',query=None,timeout=15) if False else (None,None,None)
        except Exception: pass
        try:
            st,_,p=post(PREFIX+'/real-time-quotes',{'symbols':batch})
            if 200<=st<300:
                mp=symbol_map(p)
                for c in batch:
                    o=mp.get(c)
                    if isinstance(o,dict):
                        out[c]['quoteOk']=True
                        out[c]['quote']={'price':scalar(o,('lastPrice','latestPrice','price','currentPrice','close','last')),'changePct':scalar(o,('changePct','changePercent','changeRate','percentChange','pctChange')),'amount':scalar(o,('amount','turnoverAmount','turnoverValue','value')),'keys':list(o.keys())[:30]}
        except Exception as e:
            out['_quoteError']=e.__class__.__name__
        try:
            st,_,p=post(PREFIX+'/capital-distribution',{'symbols':batch})
            if 200<=st<300:
                mp=symbol_map(p)
                for c in batch:
                    o=mp.get(c)
                    if isinstance(o,dict):
                        out[c]['capitalOk']=True
                        out[c]['capital']={'largeNetInflow':scalar(o,('largeNetInflow','largeOrderNetInflow','largeNetFlow')),'totalNetInflow':scalar(o,('totalNetInflow','netInflow','totalNetFlow')),'keys':list(o.keys())[:30]}
        except Exception as e:
            out['_capitalError']=e.__class__.__name__
    return out

def post(path,body):
    import json
    from urllib.request import Request,urlopen
    token=yg.bearer()
    req=Request(yg.BASE+path,data=json.dumps(body).encode(),method='POST',headers={'Accept':'application/json,*/*','Content-Type':'application/json','Authorization':token,'User-Agent':'AStockStrategy-Yunai/1.0'})
    with urlopen(req,timeout=20) as r:
        raw=r.read().decode('utf-8','replace')
        try: p=json.loads(raw)
        except Exception: p=raw
        return r.status,r.headers.get('Content-Type',''),p

def fetch_daily_kline(code,lmt=80):
    today=datetime.now(yg.CN).date(); start=today-timedelta(days=max(140,lmt*2))
    body={'symbols':[code],'barType':'day','startDate':start.isoformat(),'endDate':today.isoformat(),'tradeSession':'Regular','rightOption':'br'}
    try: st,_,p=post(PREFIX+'/bars-range',body)
    except Exception: return []
    if not (200<=st<300) or not isinstance(p,dict): return []
    rows=p.get(code) or ((p.get('data') or {}).get(code) if isinstance(p.get('data'),dict) else None)
    if not isinstance(rows,list): return []
    out=[]
    for x in rows:
        if not isinstance(x,dict): continue
        close=scalar(x,('close','closePrice')); amount=scalar(x,('amount','turnoverAmount','value')); dt=x.get('date') or x.get('tradeDate') or x.get('time') or x.get('timestamp')
        if close is None or dt is None: continue
        day=str(dt)[:10] if not isinstance(dt,(int,float)) else datetime.fromtimestamp(float(dt)/1000 if float(dt)>1e11 else float(dt),tz=yg.CN).strftime('%Y-%m-%d')
        out.append({'date':day,'close':close,'amount':amount})
    out.sort(key=lambda z:z['date']); return out[-lmt:]
