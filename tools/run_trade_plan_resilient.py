#!/usr/bin/env python3
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import update_trade_plan as base

_original = base.em_kline

def tx_history(code, end_day, limit=140):
    sym=base.symbol(code)
    url='https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?'+urlencode({'param':f'{sym},day,,,{limit},qfq'})
    req=Request(url,headers={'User-Agent':'Mozilla/5.0 AStockStrategy-TradePlan/1.1','Accept':'application/json,*/*','Referer':'https://gu.qq.com/'})
    with urlopen(req,timeout=12) as r:p=json.loads(r.read().decode('utf-8','replace'))
    root=(p.get('data') or {}).get(sym) or {}
    rows=root.get('qfqday') or root.get('day') or []
    out=[]
    for f in rows:
        if not isinstance(f,list) or len(f)<5 or str(f[0])>end_day:continue
        o,c,h,l=(base.num(f[i]) for i in (1,2,3,4))
        if None in (o,c,h,l):continue
        out.append({'date':str(f[0]),'open':o,'close':c,'high':h,'low':l,'amount':None})
    return out

def history(code,end_day,limit=140):
    try:
        rows=_original(code,end_day,limit)
        if len(rows)>=50:return rows
    except Exception:pass
    try:
        return tx_history(code,end_day,limit)
    except Exception:return []

base.em_kline=history

if __name__=='__main__':
    base.main()
