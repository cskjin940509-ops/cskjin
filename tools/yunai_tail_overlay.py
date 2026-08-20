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

def text(o,names):
    if not isinstance(o,dict): return None
    for k in names:
        v=o.get(k)
        if v is not None and str(v).strip(): return str(v)
    return None

def raw_value(o,names):
    if not isinstance(o,dict): return None
    for k in names:
        if k in o and o.get(k) is not None: return o.get(k)
    return None

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
    req=Request(yg.BASE+path,data=json.dumps(body).encode(),method='POST',headers={'Accept':'application/json,*/*','Content-Type':'application/json','Authorization':token,'User-Agent':'AStockStrategy-Yunai/1.6'})
    try:
        with urlopen(req,timeout=12) as r:
            raw=r.read().decode('utf-8','replace'); status=r.status; ctype=r.headers.get('Content-Type','')
    except HTTPError as e:
        raw=e.read().decode('utf-8','replace'); status=e.code; ctype=e.headers.get('Content-Type','') if e.headers else ''
    except Exception as e:
        return 599,'',{'error':e.__class__.__name__}
    try: p=json.loads(raw)
    except Exception: p=raw
    return status,ctype,p

def apply_quote(out,batch,p):
    mp=symbol_map(p)
    for c in batch:
        o=obj(mp.get(c))
        if o is not None:
            out[c]['quoteOk']=True
            out[c]['quote']={
                'price':scalar(o,('lastPrice','latestPrice','price','currentPrice','close','last')),
                'open':scalar(o,('open','openPrice')),
                'high':scalar(o,('high','highPrice')),
                'low':scalar(o,('low','lowPrice')),
                'preClose':scalar(o,('preClose','prevClose','previousClose')),
                'change':scalar(o,('change','priceChange')),
                'changePct':scalar(o,('changePct','changePercent','changeRate','percentChange','pctChange')),
                'volume':scalar(o,('volume','tradeVolume')),
                'amount':scalar(o,('amount','turnoverAmount','turnoverValue','value')),
                'turnoverRate':scalar(o,('turnoverRate','turnover')),
                'askSize':raw_value(o,('askSize','asks')),
                'bidSize':raw_value(o,('bidSize','bids')),
                'latestTime':text(o,('latestTime','quoteTime','time')),
                'timestamp':raw_value(o,('timestamp','latestTimestamp')),
                'status':text(o,('status',)),
                'tradeSession':text(o,('tradeSession','session')),
                'brokerSource':text(o,('brokerSource','source')),
                'keys':list(o.keys())[:40]
            }

def apply_capital(out,batch,p):
    mp=symbol_map(p)
    for c in batch:
        o=obj(mp.get(c))
        if o is not None:
            out[c]['capitalOk']=True
            out[c]['capital']={
                'largeNetInflow':scalar(o,('largeNetInflow','largeOrderNetInflow','largeNetFlow')),
                'totalNetInflow':scalar(o,('totalNetInflow','netInflow','totalNetFlow')),
                'capitalIn':scalar(o,('capitalIn','inflow')),
                'capitalOut':scalar(o,('capitalOut','outflow')),
                'timestamp':raw_value(o,('timestamp',)),
                'retrievedAt':text(o,('retrievedAt',)),
                'brokerSource':text(o,('brokerSource','source')),
                'keys':list(o.keys())[:40]
            }

def fetch_stock_overlay(codes):
    out={c:{'quoteOk':False,'capitalOk':False} for c in codes}
    supported=[]
    for c in codes:
        if str(c).startswith(('8','9')):
            out[c]['unsupportedMarket']='BSE'
        else:
            supported.append(c)
    for i in range(0,len(supported),10):
        batch=supported[i:i+10]
        st,_,p=post(PREFIX+'/real-time-quotes',{'symbols':batch})
        if 200<=st<300: apply_quote(out,batch,p)
        for c in batch:
            if not out[c]['quoteOk']:
                s,_,one=post(PREFIX+'/real-time-quotes',{'symbols':[c]})
                if 200<=s<300: apply_quote(out,[c],one)
        st,_,p=post(PREFIX+'/capital-distribution',{'symbols':batch})
        if 200<=st<300: apply_capital(out,batch,p)
        # Empty capital response is valid coverage state; do not fan out retries.
    return out

def fetch_daily_kline(code,lmt=80):
    if str(code).startswith(('8','9')): return []
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
