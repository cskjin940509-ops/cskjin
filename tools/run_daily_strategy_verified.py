#!/usr/bin/env python3
"""Production-safe Daily Cohort runner.

Safety invariants:
1) Historical factor bars are capped at TARGET_DATE; no future bars are visible.
2) Production Official cohorts must be generated from a frozen same-day gateway history file.
3) Every selected stock's displayed selectionPrice is the target-day *raw* close,
   independently confirmed by at least two providers within 0.1% OHLC tolerance.
4) Existing Official cohorts are immutable unless FORCE_REBUILD=1; manual historical
   reconstruction is refused when point-in-time constituent membership cannot be proven.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import run_daily_strategy_fast as base
import yunai_tail_overlay as yunai

CN = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
GATEWAY = ROOT / "astock_gateway"
SNAPS = ROOT / "astock_snapshots" / "index.json"
VERSION = "v1.8.0-verified-point-in-time-3source"
TARGET_DAY: str | None = None


def finite(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def get_json(url, referer, timeout=12):
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 AStockStrategy-Verified/1.8",
        "Accept": "application/json,*/*",
        "Referer": referer,
        "Cache-Control": "no-cache",
    })
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def safe_kline(secid: str, lmt: int = 80):
    if not TARGET_DAY:
        raise RuntimeError("TARGET_DAY not initialized")
    q = {
        "secid": secid,
        "klt": 101,
        "fqt": 1,
        "lmt": lmt,
        "end": TARGET_DAY.replace("-", ""),
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
    }
    d = (base.get_json("https://push2his.eastmoney.com/api/qt/stock/kline/get?" + urlencode(q)).get("data") or {})
    out = []
    for row in d.get("klines") or []:
        f = row.split(",")
        if len(f) >= 7 and f[0] <= TARGET_DAY and finite(f[2]) is not None:
            out.append({"date": f[0], "close": finite(f[2]), "amount": finite(f[6])})
    if any(x["date"] > TARGET_DAY for x in out):
        raise RuntimeError("future bar leaked into factor window")
    return out


def symbol(code):
    if code.startswith(("8", "9")): return "bj" + code
    return ("sh" if code.startswith(("5", "6")) else "sz") + code


def secid(code):
    return ("1." if code.startswith(("5", "6", "9")) else "0.") + code


def tencent_raw_day(code, day):
    sym = symbol(code)
    param = f"{sym},day,{day},{day},10,"
    p = get_json(
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?" + urlencode({"param": param}),
        "https://gu.qq.com/",
    )
    root = (p.get("data") or {}).get(sym) or {}
    rows = root.get("day") or []
    for f in rows:
        if isinstance(f, list) and len(f) >= 5 and f[0] == day:
            return {"open":finite(f[1]),"close":finite(f[2]),"high":finite(f[3]),"low":finite(f[4])}
    return None


def eastmoney_raw_day(code, day):
    q = {
        "secid": secid(code), "klt":101, "fqt":0, "lmt":5,
        "end":day.replace("-", ""),
        "fields1":"f1,f2,f3,f4,f5,f6",
        "fields2":"f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "ut":"fa5fd1943c7b386f172d6893dbfba10b",
    }
    p = get_json(
        "https://push2his.eastmoney.com/api/qt/stock/kline/get?" + urlencode(q),
        "https://quote.eastmoney.com/",
    )
    for raw in ((p.get("data") or {}).get("klines") or []):
        f = raw.split(",")
        if len(f) >= 5 and f[0] == day:
            return {"open":finite(f[1]),"close":finite(f[2]),"high":finite(f[3]),"low":finite(f[4])}
    return None


def _yunai_date(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            x = float(value)
            if x > 1e12: x /= 1000.0
            return datetime.fromtimestamp(x, tz=CN).strftime("%Y-%m-%d")
        except Exception:
            return None
    text = str(value).strip()
    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        return text[:10]
    if len(text) >= 8 and text[:8].isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(CN).strftime("%Y-%m-%d")
    except Exception:
        return None


def yunai_raw_day(code, day):
    if str(code).startswith(("8", "9")) or not os.environ.get("YUNAI_TOKEN", "").strip():
        return None
    status, _, payload = yunai.post(yunai.PREFIX + "/real-time-quotes", {"symbols": [code]})
    if not (200 <= status < 300):
        return None
    obj = yunai.obj(yunai.symbol_map(payload).get(code))
    if not isinstance(obj, dict):
        return None
    quote_day = None
    for key in ("timestamp", "latestTime", "time", "tradeDate", "date"):
        quote_day = _yunai_date(obj.get(key))
        if quote_day:
            break
    if quote_day != day:
        return None
    row = {
        "open": finite(obj.get("open")),
        "close": finite(obj.get("latestPrice")),
        "high": finite(obj.get("high")),
        "low": finite(obj.get("low")),
    }
    if any(row[k] is None for k in ("open", "close", "high", "low")):
        return None
    return row


def rel_diff(a, b):
    if a is None or b is None or min(abs(a), abs(b)) == 0: return None
    return abs(a-b) / min(abs(a), abs(b))


def pair_diff(a, b):
    diffs=[]
    for field in ("open","close","high","low"):
        d=rel_diff(finite(a.get(field)), finite(b.get(field)))
        if d is None:
            return None
        diffs.append(d)
    return max(diffs) if diffs else None


def verify_price(code, day):
    providers = [("腾讯", tencent_raw_day), ("东方财富", eastmoney_raw_day)]
    if os.environ.get("YUNAI_TOKEN", "").strip() and not str(code).startswith(("8", "9")):
        providers.append(("Yunai", yunai_raw_day))
    checks=[]
    valid=[]
    for name, fn in providers:
        try:
            row=fn(code, day)
            checks.append({"provider":name,"row":row})
            if row and all(finite(row.get(k)) is not None for k in ("open","close","high","low")):
                valid.append((name,row))
        except Exception as e:
            checks.append({"provider":name,"row":None,"error":e.__class__.__name__})
    best=None
    for i in range(len(valid)):
        for j in range(i+1,len(valid)):
            mx=pair_diff(valid[i][1], valid[j][1])
            if mx is not None and (best is None or mx < best[0]):
                best=(mx,valid[i],valid[j])
    if not best or best[0] > 0.001:
        return {"verified":False,"checks":checks,"reason":"fewer-than-two-agreeing-raw-providers",
                "bestMaxRelDiff":best[0] if best else None}
    mx,a,b=best
    return {
        "verified":True,
        "rawClose":finite(a[1].get("close")),
        "maxRelDiff":mx,
        "providers":[a[0],b[0]],
        "checks":checks,
        "rule":"至少两个独立源未复权OHLC最大相对差<=0.1%",
    }


def existing_official(day):
    if not SNAPS.exists(): return None
    arr=json.loads(SNAPS.read_text(encoding="utf-8"))
    return next((x for x in arr if x.get("date")==day and x.get("status")=="Official"), None)


def load_frozen_payload(day):
    path=GATEWAY/"history"/f"{day}.json"
    if not path.exists():
        raise RuntimeError("缺少当日冻结市场快照，禁止重建 Official")
    payload=json.loads(path.read_text(encoding="utf-8"))
    source=(payload.get("marketSnapshot") or {}).get("sourceDate")
    if source != day:
        raise RuntimeError(f"冻结快照日期不匹配: {source} != {day}")
    if not (payload.get("boardHeatmap") or {}).get("industry"):
        raise RuntimeError("冻结板块截面缺失")
    return payload


def main():
    global TARGET_DAY
    requested=os.getenv("TARGET_DATE", "").strip()
    if requested:
        TARGET_DAY=requested
    else:
        latest=json.loads((GATEWAY/"latest.json").read_text(encoding="utf-8"))
        TARGET_DAY=(latest.get("marketSnapshot") or {}).get("sourceDate")
    if not TARGET_DAY:
        raise RuntimeError("无法确定目标交易日")

    prior=existing_official(TARGET_DAY)
    if prior and os.getenv("FORCE_REBUILD", "0") != "1":
        print(json.dumps({"state":"immutable","date":TARGET_DAY,"reason":"Official cohort already exists"},ensure_ascii=False))
        return

    payload=load_frozen_payload(TARGET_DAY)
    now=datetime.now(CN)
    target=datetime.strptime(TARGET_DAY, "%Y-%m-%d").date()
    if now.date() != target:
        raise RuntimeError("历史重建缺少 point-in-time 成分股快照；禁止生成 Official")

    base.kline=safe_kline
    base.VERSION=VERSION
    selected=base.choose_sectors(payload)
    stocks,pools=base.choose_stocks(selected)

    required=sorted({c for values in pools.values() for c in (values or [])})
    validations={code:verify_price(code,TARGET_DAY) for code in required}
    failed=[c for c,v in validations.items() if not v.get("verified")]
    if failed:
        raise RuntimeError("未通过至少双源收盘价校验: " + ",".join(failed))

    by_code={s["code"]:s for s in stocks}
    for code,v in validations.items():
        if code in by_code:
            by_code[code]["price"]=v["rawClose"]
            by_code[code]["priceValidation"]={k:v.get(k) for k in ("verified","maxRelDiff","providers","rule")}

    base.freeze(TARGET_DAY,payload,selected,stocks,pools)
    arr=json.loads(SNAPS.read_text(encoding="utf-8"))
    used_providers=sorted({p for v in validations.values() for p in (v.get("providers") or [])})
    for item in arr:
        if item.get("date") != TARGET_DAY: continue
        item["strategyVersion"]=VERSION
        item["dataValidation"]={
            "status":"Verified",
            "priceBasis":"未复权实际收盘价",
            "factorPriceBasis":"前复权，仅用于RS/MTA等因子",
            "factorBarsCutoff":TARGET_DAY,
            "priceProviders":used_providers,
            "stockCount":len(required),
            "rule":"所有入池股票至少两个独立源未复权OHLC最大相对差<=0.1%",
        }
        item["audit"]={
            "status":"Verified",
            "eligibleForPerformanceComparison":True,
            "issues":[],
            "auditedAt":datetime.now(CN).isoformat(timespec="seconds"),
            "note":"生产扫描通过目标日时点和至少双源价格门禁。",
        }
        for code,v in validations.items():
            meta=(item.get("stocks") or {}).get(code)
            if meta is not None:
                meta["selectionPrice"]=v["rawClose"]
                meta["priceValidation"]={
                    "status":"Verified","providers":v.get("providers") or [],
                    "maxRelDiff":v.get("maxRelDiff"),"basis":"raw-close"
                }
        break
    SNAPS.write_text(json.dumps(arr,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"state":"verified-official","date":TARGET_DAY,"stocks":len(required),"version":VERSION,"providers":used_providers},ensure_ascii=False))


if __name__ == "__main__":
    main()
