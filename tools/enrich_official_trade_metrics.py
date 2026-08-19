#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import run_daily_strategy_verified as verified

CN = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
SNAPS = ROOT / "astock_snapshots" / "index.json"


def finite(v):
    try:
        x = float(v)
        return x if x == x and abs(x) != float("inf") else None
    except Exception:
        return None


def pct(a, b):
    a, b = finite(a), finite(b)
    if a is None or b in (None, 0):
        return None
    return round((a / b - 1.0) * 100.0, 4)


def choose_verified_row(code: str, day: str):
    result = verified.verify_price(code, day)
    if not result.get("verified"):
        return None, result
    providers = set(result.get("providers") or [])
    candidates = []
    for check in result.get("checks") or []:
        if check.get("provider") not in providers:
            continue
        row = check.get("row")
        if isinstance(row, dict) and all(finite(row.get(k)) is not None for k in ("open", "close", "high", "low")):
            candidates.append(row)
    if not candidates:
        return None, result
    row = candidates[0]
    return {
        "open": finite(row.get("open")),
        "close": finite(row.get("close")),
        "high": finite(row.get("high")),
        "low": finite(row.get("low")),
    }, result


def enrich_item(item: dict) -> tuple[int, int]:
    day = str(item.get("date") or "")
    if item.get("status") != "Official" or not day:
        return 0, 0
    stocks = item.get("stocks") or {}
    pool_codes = {str(c) for vals in (item.get("pools") or {}).values() for c in (vals or [])}
    codes = sorted(pool_codes | set(map(str, stocks.keys())))
    ok = 0
    failed = 0
    for code in codes:
        meta = stocks.get(code)
        if not isinstance(meta, dict):
            continue
        row, validation = choose_verified_row(code, day)
        if not row:
            failed += 1
            continue
        op, cl, hi, lo = row["open"], row["close"], row["high"], row["low"]
        meta["dayOpen"] = op
        meta["dayClose"] = cl
        meta["dayHigh"] = hi
        meta["dayLow"] = lo
        meta["dayChangePct"] = pct(cl, op)
        meta["dayRangePct"] = pct(hi, lo)
        meta["theoreticalLowToHighPct"] = pct(hi, lo)
        meta["tradeFacts"] = {
            "status": "Verified",
            "basis": "未复权日线",
            "providers": validation.get("providers") or [],
            "maxRelDiff": validation.get("maxRelDiff"),
            "note": "最低到最高仅为理论区间，不代表按时间顺序可实现收益。",
        }
        ok += 1

    def pool_day_metrics(pool_codes):
        vals = []
        ranges = []
        for code in pool_codes or []:
            meta = stocks.get(str(code)) or {}
            v = finite(meta.get("changePct"))
            if v is None:
                v = finite(meta.get("dayChangePct"))
            r = finite(meta.get("dayRangePct"))
            if v is not None:
                vals.append(v)
            if r is not None:
                ranges.append(r)
        if not vals and not ranges:
            return {}
        out = {"members": len(vals)}
        if vals:
            out["averageDayChangePct"] = round(sum(vals) / len(vals), 4)
            out["positiveRate"] = round(sum(v > 0 for v in vals) / len(vals), 4)
        if ranges:
            out["averageDayRangePct"] = round(sum(ranges) / len(ranges), 4)
        return out

    item["sameDayPerformance"] = {
        pool: pool_day_metrics(vals)
        for pool, vals in (item.get("pools") or {}).items()
    }
    item["tradeFactsUpdatedAt"] = datetime.now(CN).isoformat(timespec="seconds")
    item["trackingState"] = {
        "entryRule": "信号日后一交易日开盘",
        "state": "等待下一交易日可成交开盘" if day >= datetime.now(CN).strftime("%Y-%m-%d") else "可更新后续收益",
        "note": "信号日当天涨跌属于当日行情表现，不计作策略可交易收益。",
    }
    return ok, failed


def main():
    if not SNAPS.exists():
        raise RuntimeError("snapshot index missing")
    arr = json.loads(SNAPS.read_text(encoding="utf-8"))
    target = os.getenv("TARGET_DATE", "").strip()
    candidates = [x for x in arr if x.get("status") == "Official" and (not target or x.get("date") == target)]
    if not target and candidates:
        latest = max(x.get("date", "") for x in candidates)
        candidates = [x for x in candidates if x.get("date") == latest]
    ok = failed = 0
    for item in candidates:
        a, b = enrich_item(item)
        ok += a
        failed += b
    SNAPS.write_text(json.dumps(arr, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"state":"updated","cohorts":len(candidates),"stockFacts":ok,"failed":failed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
