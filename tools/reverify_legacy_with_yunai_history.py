#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime

import reverify_legacy_cohorts as audit
import run_daily_strategy_verified as verified
import yunai_tail_overlay as yunai
import enrich_yunai_gateway as yg


def yunai_historical_raw_day(code: str, day: str):
    if str(code).startswith(("8", "9")):
        return None
    body = {
        "symbols": [str(code)],
        "barType": "day",
        "startDate": day,
        "endDate": day,
        "tradeSession": "Regular",
        "rightOption": "nr",
    }
    status, _, payload = yunai.post(yunai.PREFIX + "/bars-range", body)
    if not (200 <= status < 300) or not isinstance(payload, dict):
        return None
    rows = payload.get(str(code))
    if rows is None and isinstance(payload.get("data"), dict):
        rows = payload["data"].get(str(code))
    if not isinstance(rows, list):
        return None
    for x in rows:
        if not isinstance(x, dict):
            continue
        dt = x.get("date") or x.get("tradeDate") or x.get("time") or x.get("timestamp")
        if dt is None:
            continue
        if isinstance(dt, (int, float)):
            value = float(dt)
            if value > 1e11:
                value /= 1000.0
            bar_day = datetime.fromtimestamp(value, tz=yg.CN).strftime("%Y-%m-%d")
        else:
            text = str(dt)
            bar_day = text[:10] if len(text) >= 10 else text
        if bar_day != day:
            continue
        row = {
            "open": yunai.scalar(x, ("open", "openPrice")),
            "close": yunai.scalar(x, ("close", "closePrice", "latestPrice")),
            "high": yunai.scalar(x, ("high", "highPrice")),
            "low": yunai.scalar(x, ("low", "lowPrice")),
        }
        if all(verified.finite(row[k]) is not None for k in ("open", "close", "high", "low")):
            return row
    return None


# Legacy audit calls verified.verify_price(); replacing only the Yunai provider
# gives historical audits a true unadjusted bars-range source while retaining
# the same "at least two independent providers within 0.1% OHLC" gate.
verified.yunai_raw_day = yunai_historical_raw_day

if __name__ == "__main__":
    audit.main()
