#!/usr/bin/env python3
from __future__ import annotations
import json, math
from datetime import datetime, timedelta
from urllib.error import HTTPError
from urllib.request import Request, urlopen
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

def obj(v):
    if isinstance(v,dict): return v
    if isinstance(v,list):
        for x in reversed(v):
            if isinstance(x,dict): return x
    return None

def scalar(o,names):
    if not isinstance(o,dict): return None
    for k in names:
        if k in o:
            v=finite(o.get(k))
            if v is not None: return v
    return None

def post(path,body):
    token=yg.bearer()
    req=Request(yg.BASE+path,data=json.dumps(body).encode(),method='POST',headers={'Accept':'application/json,*/*','Content-Type':'application/json','Authorization':token,'User-Agent':'AStockStrategy-Yunai/1.3'})
    try:
        with urlopen(req,timeout=20) as r:
            raw=r.read().decode('utf-8','replace'); status=r.status; ctype=r.headers.get('Content-Type','')
    except HTTPError as e:
        raw=e.read().decode('utf-8','replace'); status=e.code; ctype=e.headers.get('Content-Type','') if e.headers else ''
    try: p=json.loads(raw)
    except Exception: p=raw
    return status,ctype,p

def apply_quote(out,batch,p):
    mp=symbol_map(p)
    for c in batch:
        o=obj(mp.get(c))
        if o is not None:
            out[c]['quoteOk']=True
            out[c]['quote']={'price':scalar(o,('lastPrice','latestPrice','price','currentPrice','close','last')),'changePct':scalar(o,('changePct','changePercent','changeRate','percentChange','pctChange')),'amount':scalar(o,('amount','turnoverAmount','turnoverValue','value')),'keys':list(o.keys())[:30]}

def apply_capital(out,batch,p):
    mp=symbol_map(p)
    for c in batch:
        o=obj(mp.get(c))
        if o is not None:
            out[c]['capitalOk']=True
            out[c]['capital']={'largeNetInflow':scalar(o,('largeNetInflow','largeOrderNetInflow','largeNetFlow')),'totalNetInflow':scalar(o,('totalNetInflow','netInflow','totalNetFlow')),'keys':list(o.keys())[:30]}

def fetch_stock_overlay(codes):
    out={c:{'quoteOk':False,'capitalOk':False} for c in codes}
    for i in range(0,len(codes),10):
        batch=codes[i:i+10]
        st,_,p=post(PREFIX+'/real-time-quotes',{'symbols':batch})
        if 200<=st<300: apply_quote(out,batch,p)
        for c in batch:
            if not out[c]['quoteOk']:
                s,_,one=post(PREFIX+'/real-time-quotes',{'symbols':[c]})
                if 200<=s<300: apply_quote(out,[c],one)
        st,_,p=post(PREFIX+'/capital-distribution',{'symbols':batch})
        if 200<=st<300: apply_capital(out,batch,p)
        for c in batch:
            if not out[c]['capitalOk']:
                s,_,one=post(PREFIX+'/capital-distribution',{'symbols':[c]})
                if 200<=s<300: apply_capital(out,[c],one)
    return out

def fetch_daily_kline(code,lmt=80):
    today=datetime.now(yg.CN).date(); start=today-timedelta(days=max(140,lmt*2))
    body={'symbols':[code],'barType':'day','startDate':start.isoformat(),'endDate':today.isoformat(),'tradeSession':'Regular','rightOption':'br'}
    st,_,p=post(PREFIX+'/bars-range',body)
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
