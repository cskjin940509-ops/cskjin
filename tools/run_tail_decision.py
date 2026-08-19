#!/usr/bin/env python3
"""Freeze a point-in-time 14:30 tail-decision cohort.

This is deliberately separate from the post-close Official Daily Cohort.
Only data observable at capture time is used. The result is immutable for the day
unless FORCE_REBUILD=1 is explicitly set.
"""
from __future__ import annotations

import json
import math
import os
import statistics
import time
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import run_daily_strategy_fast as base
import update_market_gateway as gw
from bse_market_mapping import eastmoney_secid

CN = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "astock_tail"
HIST = OUT / "history"
VERSION = "v1.0-tail-1430-point-in-time"
PREFERRED_EM_HOST = "push2.eastmoney.com"
USED_DELAYED = False


def finite(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def get_json(url: str, referer: str = "https://quote.eastmoney.com/", timeout: int = 12):
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 AStockStrategy-Tail/1.0",
        "Accept": "application/json,*/*",
        "Referer": referer,
        "Cache-Control": "no-cache",
    })
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def em_clist_host(host: str, fs: str, fields: str, pz: int = 120, fid: str = "f6"):
    q = {
        "pn": 1, "pz": pz, "po": 1, "np": 1, "fltt": 2, "invt": 2,
        "fid": fid, "fs": fs, "fields": fields,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "_": int(time.time() * 1000),
    }
    p = get_json(f"https://{host}/api/qt/clist/get?" + urlencode(q))
    return (p.get("data") or {}).get("diff") or []


def fetch_clist(fs: str, fields: str, pz: int = 120, fid: str = "f6"):
    global PREFERRED_EM_HOST, USED_DELAYED
    hosts = [PREFERRED_EM_HOST] + [h for h in ("push2.eastmoney.com", "push2delay.eastmoney.com") if h != PREFERRED_EM_HOST]
    last = None
    for host in hosts:
        try:
            rows = em_clist_host(host, fs, fields, pz, fid)
            if rows:
                PREFERRED_EM_HOST = host
                if host == "push2delay.eastmoney.com":
                    USED_DELAYED = True
                return rows
        except Exception as e:
            last = e
    raise RuntimeError(last or "东方财富列表不可用")


def tail_boards(kind: str):
    fs = "m:90+t:2+f:!50" if kind == "industry" else "m:90+t:3+f:!50"
    rows = fetch_clist(fs, "f3,f6,f12,f14,f62,f184,f104,f105,f106", 500, "f3")
    out = []
    for x in rows:
        up, down, flat = int(x.get("f104") or 0), int(x.get("f105") or 0), int(x.get("f106") or 0)
        total = up + down + flat
        out.append({
            "boardCode": str(x.get("f12") or ""),
            "name": x.get("f14") or "",
            "changePct": finite(x.get("f3")),
            "amount": finite(x.get("f6")),
            "mainNetFlow": finite(x.get("f62")),
            "mainFlowPct": finite(x.get("f184")),
            "up": up, "down": down, "flat": flat,
            "breadthPct": (100.0 * up / total) if total else None,
            "source": "东方财富延迟板块" if PREFERRED_EM_HOST.endswith("delay.eastmoney.com") else "东方财富实时板块",
        })
    return out


def safe_kline(secid: str, lmt: int = 80):
    day = datetime.now(CN).strftime("%Y-%m-%d")
    q = {
        "secid": secid, "klt": 101, "fqt": 1, "lmt": lmt,
        "end": day.replace("-", ""),
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
    }
    d = (base.get_json("https://push2his.eastmoney.com/api/qt/stock/kline/get?" + urlencode(q)).get("data") or {})
    out = []
    for row in d.get("klines") or []:
        f = row.split(",")
        if len(f) >= 7 and f[0] <= day and finite(f[2]) is not None:
            out.append({"date": f[0], "close": finite(f[2]), "amount": finite(f[6])})
    return out


def limit_pct(code: str) -> float:
    if code.startswith(("8", "9")):
        return 30.0
    if code.startswith(("30", "68")):
        return 20.0
    return 10.0


def tail_risk(stock: dict):
    ch = finite(stock.get("changePct"))
    lim = limit_pct(stock.get("code", ""))
    if ch is None:
        return "价格变化待同步", False
    if ch >= lim - 0.6:
        return "接近涨停，尾盘可交易性差", False
    if ch <= -lim + 0.6:
        return "接近跌停，尾盘可交易性差", False
    if ch >= lim * 0.68:
        return "涨幅较大，追高风险", True
    return "正常", True


def current_index_payload():
    syms = ["sh000001", "sz399006", "sh000688", "sh000300", "sh000852"]
    q = gw.tencent_quotes(syms)
    provider_dates = sorted({x.get("quoteDate") for x in q.values() if x.get("quoteDate")})
    return q, provider_dates[-1] if provider_dates else None


def build_payload(now: datetime):
    global USED_DELAYED
    USED_DELAYED = False
    quotes, provider_date = current_index_payload()
    today_compact = now.strftime("%Y%m%d")
    if provider_date != today_compact:
        raise RuntimeError(f"腾讯指数行情日期不是今天: {provider_date}")

    # Require reasonably fresh index timestamp. This prevents a stale prior-session
    # cache from becoming a tail trading signal.
    stamps = []
    for x in quotes.values():
        raw = x.get("quoteTimeRaw")
        if raw and len(raw) >= 14 and raw[:14].isdigit():
            try:
                stamps.append(datetime.strptime(raw[:14], "%Y%m%d%H%M%S").replace(tzinfo=CN))
            except Exception:
                pass
    max_stamp = max(stamps) if stamps else None
    quote_age = (now - max_stamp).total_seconds() if max_stamp else None
    if quote_age is None or quote_age > 8 * 60:
        raise RuntimeError(f"指数行情时间戳过旧: age={quote_age}")

    industry = tail_boards("industry")
    concept = tail_boards("concept")
    if not industry:
        raise RuntimeError("行业板块为空")

    payload = {
        "marketSnapshot": {
            "sourceDate": now.strftime("%Y-%m-%d"),
            "availableAt": now.isoformat(timespec="seconds"),
            "verifiedToday": True,
            "indices": gw.index_snapshot(quotes),
        },
        "boardHeatmap": {
            "industry": industry,
            "concept": concept,
            "sourceDate": now.strftime("%Y-%m-%d"),
            "availableAt": now.isoformat(timespec="seconds"),
        },
    }
    return payload, quote_age


def stock_view(s: dict, memberships: list[str]):
    risk, tradable = tail_risk(s)
    score = finite(s.get("score")) or 0.0
    flow = finite(s.get("flowScore")) or 0.0
    sector = finite(s.get("sectorScore")) or 0.0
    tail_score = 0.55 * score + 0.30 * flow + 0.15 * sector
    return {
        "code": s.get("code"), "name": s.get("name"), "sector": s.get("sector"),
        "price": finite(s.get("price")), "changePct": finite(s.get("changePct")),
        "amount": finite(s.get("amount")), "turnover": finite(s.get("turnover")),
        "mainNetFlow": finite(s.get("mainNetFlow")), "mainFlowPct": finite(s.get("mainFlowPct")),
        "RS20": round(100 * s["rs20"], 2) if s.get("rs20") is not None else None,
        "RS60": round(100 * s["rs60"], 2) if s.get("rs60") is not None else None,
        "MTA": s.get("mta"), "baseScore": round(score, 2), "flowScore": round(flow, 2),
        "tailScore": round(tail_score, 2), "pools": memberships,
        "risk": risk, "tailTradable": tradable,
        "reason": s.get("reason"),
    }


def main():
    now = datetime.now(CN)
    day = now.strftime("%Y-%m-%d")
    if now.weekday() >= 5:
        print(json.dumps({"state": "skip", "reason": "weekend", "date": day}, ensure_ascii=False))
        return

    allow_any = os.getenv("ALLOW_ANY_TIME", "0") == "1"
    if not allow_any and not (dtime(14, 25) <= now.time() < dtime(15, 0)):
        print(json.dumps({"state": "skip", "reason": "outside-tail-window", "capturedAt": now.isoformat(timespec="seconds")}, ensure_ascii=False))
        return

    HIST.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    hist_path = HIST / f"{day}.json"
    if hist_path.exists() and os.getenv("FORCE_REBUILD", "0") != "1":
        existing = json.loads(hist_path.read_text(encoding="utf-8"))
        (OUT / "latest.json").write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"state": "immutable", "date": day, "capturedAt": existing.get("capturedAt")}, ensure_ascii=False))
        return

    payload, quote_age = build_payload(now)

    # Point-in-time factor safety + BSE-safe market IDs.
    base.kline = safe_kline
    base.sid = lambda code: eastmoney_secid(code)
    base.em_clist = fetch_clist

    selected = base.choose_sectors(payload)
    confirmed = [x for x in selected if x.get("status") == "确认主线"]
    candidates = [x for x in selected if x.get("status") != "确认主线"]

    stocks = []
    raw_pools = {"B0": [], "B3": []}
    if confirmed:
        stocks, raw = base.choose_stocks(confirmed)
        raw_pools["B0"] = raw.get("B0") or []
        raw_pools["B3"] = raw.get("B3") or []

    by_code = {s.get("code"): s for s in stocks if s.get("code")}
    tb0 = [c for c in raw_pools["B0"] if c in by_code and tail_risk(by_code[c])[1]]
    tb3 = [c for c in raw_pools["B3"] if c in by_code and tail_risk(by_code[c])[1]]
    intersection = set(tb0) & set(tb3)
    core = sorted(
        intersection,
        key=lambda c: 0.55 * (finite(by_code[c].get("score")) or 0.0)
                    + 0.30 * (finite(by_code[c].get("flowScore")) or 0.0)
                    + 0.15 * (finite(by_code[c].get("sectorScore")) or 0.0),
        reverse=True,
    )[:8]

    membership = {}
    for c in set(tb0 + tb3 + core):
        p = []
        if c in tb0: p.append("TB0")
        if c in tb3: p.append("TB3")
        if c in core: p.append("TailCore")
        membership[c] = p

    stock_rows = [stock_view(by_code[c], membership[c]) for c in membership]
    stock_rows.sort(key=lambda x: x.get("tailScore") or 0.0, reverse=True)

    board_source = "东方财富延迟源（约15分钟）" if USED_DELAYED else "东方财富实时"
    result = {
        "schemaVersion": 1,
        "date": day,
        "status": "TailDecision",
        "strategyVersion": VERSION,
        "scheduledFor": f"{day}T14:30:00+08:00",
        "capturedAt": now.isoformat(timespec="seconds"),
        "marketQuoteAgeSec": round(quote_age, 1),
        "dataSource": f"腾讯指数行情 + {board_source}",
        "boardSource": board_source,
        "factorCutoff": now.isoformat(timespec="seconds"),
        "confirmedMainlines": confirmed,
        "candidateMainlines": candidates,
        "pools": {"TB0": tb0, "TB3": tb3, "TailCore": core},
        "stocks": {x["code"]: x for x in stock_rows},
        "noTrade": len(confirmed) == 0 or len(core) == 0,
        "confidence": "中" if USED_DELAYED else "中高",
        "note": "14:30尾盘决策池只使用捕获时已可获得的数据；不等同于收盘Official。TB0=基础强度，TB3=主力资金确认，TailCore=TB0与TB3交集并按尾盘综合分排序；B1两融/B2 ETF申赎未同步时不伪造。",
        "executionNote": "用于尾盘决策参考；接近涨跌停的股票从可交易池剔除。收盘后会重新计算，14:30结果保持冻结以便复盘。",
    }

    hist_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "latest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "state": "tail-frozen", "date": day, "capturedAt": result["capturedAt"],
        "confirmedMainlines": [x.get("name") for x in confirmed],
        "TB0": len(tb0), "TB3": len(tb3), "TailCore": len(core),
        "boardSource": board_source, "noTrade": result["noTrade"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
