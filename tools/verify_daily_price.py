#!/usr/bin/env python3
from __future__ import annotations

import json, math, os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CN = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "astock_gateway" / "validation"
UA = "Mozilla/5.0 AStockStrategy-Validator/1.0"


def finite(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def get_text(url, referer=None):
    h = {"User-Agent": UA, "Accept": "*/*", "Cache-Control": "no-cache"}
    if referer: h["Referer"] = referer
    with urlopen(Request(url, headers=h), timeout=15) as r:
        return r.read().decode("utf-8", "replace")


def market_symbol(code):
    if code.startswith(("8", "9")): return "bj" + code
    return ("sh" if code.startswith(("5", "6")) else "sz") + code


def secid(code):
    return ("1." if code.startswith(("5", "6", "9")) else "0.") + code


def parse_tx_rows(payload, sym):
    root = (payload.get("data") or {}).get(sym) or {}
    rows = root.get("day") or root.get("qfqday") or []
    out = {}
    for f in rows:
        if not isinstance(f, list) or len(f) < 5: continue
        out[f[0]] = {
            "date": f[0], "open": finite(f[1]), "close": finite(f[2]),
            "high": finite(f[3]), "low": finite(f[4]),
            "volume": finite(f[5]) if len(f) > 5 else None,
        }
    return out


def tencent(code, day, adjust):
    sym = market_symbol(code)
    fq = "qfq" if adjust else ""
    param = f"{sym},day,{day},{day},10,{fq}"
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?" + urlencode({"param": param})
    payload = json.loads(get_text(url, "https://gu.qq.com/"))
    row = parse_tx_rows(payload, sym).get(day)
    return {"provider":"腾讯", "adjust":"qfq" if adjust else "raw", "row":row, "urlKind":"fqkline"}


def eastmoney(code, day, adjust):
    q = {
        "secid": secid(code), "klt": 101, "fqt": 1 if adjust else 0,
        "lmt": 5, "end": day.replace("-", ""),
        "fields1":"f1,f2,f3,f4,f5,f6",
        "fields2":"f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "ut":"fa5fd1943c7b386f172d6893dbfba10b",
    }
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?" + urlencode(q)
    payload = json.loads(get_text(url, "https://quote.eastmoney.com/"))
    rows = ((payload.get("data") or {}).get("klines") or [])
    row = None
    for raw in rows:
        f = raw.split(",")
        if len(f) >= 7 and f[0] == day:
            row = {"date":f[0], "open":finite(f[1]), "close":finite(f[2]), "high":finite(f[3]), "low":finite(f[4]), "volume":finite(f[5]), "amount":finite(f[6])}
            break
    return {"provider":"东方财富", "adjust":"qfq" if adjust else "raw", "row":row, "urlKind":"kline"}


def max_rel_diff(rows):
    vals=[]
    for field in ("open","close","high","low"):
        xs=[finite((x.get("row") or {}).get(field)) for x in rows]
        xs=[x for x in xs if x is not None and x != 0]
        if len(xs)>=2:
            lo,hi=min(xs),max(xs)
            vals.append((hi-lo)/lo)
    return max(vals) if vals else None


def validate_ohlc(row):
    if not row: return ["missing-row"]
    o,c,h,l=[finite(row.get(k)) for k in ("open","close","high","low")]
    errs=[]
    if any(x is None for x in (o,c,h,l)): errs.append("missing-ohlc")
    elif h < max(o,c) or l > min(o,c) or l > h: errs.append("invalid-ohlc")
    return errs


def main():
    code=os.getenv("SYMBOL","002371").strip()
    day=os.getenv("TARGET_DATE","2026-08-18").strip()
    checks=[]; errors=[]
    for fn in (tencent, eastmoney):
        for adjust in (False, True):
            try: checks.append(fn(code,day,adjust))
            except Exception as e:
                checks.append({"provider":fn.__name__,"adjust":"qfq" if adjust else "raw","row":None,"error":f"{e.__class__.__name__}: {e}"})
    raw=[x for x in checks if x.get("adjust")=="raw" and x.get("row")]
    qfq=[x for x in checks if x.get("adjust")=="qfq" and x.get("row")]
    for x in checks:
        for e in validate_ohlc(x.get("row")): errors.append(f"{x.get('provider')}/{x.get('adjust')}:{e}")
    raw_diff=max_rel_diff(raw); qfq_diff=max_rel_diff(qfq)
    verified=bool(len(raw)>=2 and raw_diff is not None and raw_diff <= 0.001)
    report={
        "symbol":code,"date":day,"generatedAt":datetime.now(CN).isoformat(timespec="seconds"),
        "checks":checks,"rawCrossSourceMaxRelDiff":raw_diff,"qfqCrossSourceMaxRelDiff":qfq_diff,
        "verified":verified,"errors":errors,
        "rule":"正式价格必须至少两个独立源的未复权OHLC一致（最大相对差<=0.1%）；复权价只用于收益/因子，不作为实际成交价展示。",
    }
    OUT.mkdir(parents=True,exist_ok=True)
    path=OUT/f"{day}-{code}.json"
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))
    if not verified: raise SystemExit(2)

if __name__=="__main__": main()
