#!/usr/bin/env python3
"""Verified wrapper around the forward tracker.

- Returns/MFE/MAE continue to use qfq bars for corporate-action continuity.
- Displayed/audited entryPrice is the unadjusted next-session open.
- The raw open must agree between Tencent and Eastmoney within 0.1%.
- LegacyUnverified cohorts are excluded from strategy-performance comparison.
"""
from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import update_strategy_backtest as legacy

VERSION = "v1.1-next-open-verified-raw-entry"
_original_fetch = legacy.fetch_kline
_original_performance = legacy.performance_for
_original_trackable = legacy.snapshot_is_trackable


def request_json(url, referer):
    req=Request(url,headers={
        "User-Agent":"Mozilla/5.0 AStockStrategy-Backtest-Verified/1.1",
        "Accept":"application/json,*/*","Referer":referer,"Cache-Control":"no-cache"})
    with urlopen(req,timeout=12) as r:
        return json.loads(r.read().decode("utf-8","replace"))


def symbol(code):
    if code.startswith(("8","9")): return "bj"+code
    return ("sh" if code=="000300" or code.startswith(("5","6")) else "sz")+code


def raw_tencent(code,limit=620):
    sym=symbol(code)
    p=request_json("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"+urlencode({"param":f"{sym},day,,,{limit},"}),"https://gu.qq.com/")
    root=(p.get("data") or {}).get(sym) or {}; rows=root.get("day") or []
    out={}
    for f in rows:
        if isinstance(f,list) and len(f)>=5:
            out[f[0]]={"open":legacy.finite(f[1]),"close":legacy.finite(f[2]),"high":legacy.finite(f[3]),"low":legacy.finite(f[4])}
    return out


def raw_eastmoney(code,limit=620):
    q={"secid":legacy.secid(code),"klt":101,"fqt":0,"lmt":limit,"end":"20500101",
       "fields1":"f1,f2,f3,f4,f5,f6","fields2":"f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
       "ut":"fa5fd1943c7b386f172d6893dbfba10b"}
    p=request_json("https://push2his.eastmoney.com/api/qt/stock/kline/get?"+urlencode(q),"https://quote.eastmoney.com/")
    out={}
    for raw in ((p.get("data") or {}).get("klines") or []):
        f=raw.split(",")
        if len(f)>=5:
            out[f[0]]={"open":legacy.finite(f[1]),"close":legacy.finite(f[2]),"high":legacy.finite(f[3]),"low":legacy.finite(f[4])}
    return out


def max_diff(a,b):
    ds=[]
    for k in ("open","close","high","low"):
        x=legacy.finite((a or {}).get(k)); y=legacy.finite((b or {}).get(k))
        if x is None or y is None or min(abs(x),abs(y))==0: continue
        ds.append(abs(x-y)/min(abs(x),abs(y)))
    return max(ds) if ds else None


def fetch_kline_verified(code,limit=620):
    adjusted=_original_fetch(code,limit)
    try: t=raw_tencent(code,limit)
    except Exception: t={}
    try: e=raw_eastmoney(code,limit)
    except Exception: e={}
    for row in adjusted:
        d=row.get("date"); tr=t.get(d); er=e.get(d); diff=max_diff(tr,er)
        if tr and er and diff is not None and diff<=0.001:
            row["rawOpenVerified"]=legacy.finite(tr.get("open"))
            row["rawCloseVerified"]=legacy.finite(tr.get("close"))
            row["rawMaxRelDiff"]=diff
            row["rawProviders"]=["腾讯","东方财富"]
    return adjusted


def performance_verified(rows,cohort_date,benchmark):
    result=_original_performance(rows,cohort_date,benchmark)
    if result is None: return None
    entry_date=result.get("entryDate")
    entry_row=next((x for x in rows if x.get("date")==entry_date),None)
    raw_open=legacy.finite((entry_row or {}).get("rawOpenVerified"))
    if raw_open is None:
        # Never overwrite an auditable performance record with a single-source price.
        return None
    adjusted_entry=result.get("entryPrice")
    result["returnEntryPriceAdjusted"]=adjusted_entry
    result["entryPrice"]=legacy.rounded(raw_open)
    result["source"]="腾讯+东方财富未复权入场价；收益使用前复权日线"
    result["priceValidation"]={
        "status":"Verified","basis":"raw-open","providers":(entry_row or {}).get("rawProviders") or [],
        "maxRelDiff":(entry_row or {}).get("rawMaxRelDiff"),
        "returnBasis":"qfq",
    }
    return result


def trackable_verified(snapshot,now):
    audit=snapshot.get("audit") or {}
    if audit.get("eligibleForPerformanceComparison") is False:
        return False
    return _original_trackable(snapshot,now)


legacy.fetch_kline=fetch_kline_verified
legacy.performance_for=performance_verified
legacy.snapshot_is_trackable=trackable_verified
legacy.VERSION=VERSION

if __name__=="__main__":
    legacy.main()
