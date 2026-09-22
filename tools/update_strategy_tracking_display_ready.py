#!/usr/bin/env python3
"""Display-ready verified forward tracking.

Goals:
- Keep the original next-trading-day-open tracking convention.
- Calculate tracking for every frozen Official cohort, even when an older cohort is
  audit-ineligible for leaderboard/model statistics. Such results are marked ReferenceOnly.
- Use any available approved raw provider; multiple feeds are diagnostic only.
- Preserve the stronger BSE handling from update_strategy_backtest_verified_bse.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

import update_strategy_backtest as legacy
import update_strategy_backtest_verified_bse as bse  # applies BSE market mapping/quote patch
import update_strategy_backtest_verified as verified
import run_daily_strategy_verified as daily_verified

CN = legacy.CN
SNAPSHOTS = legacy.SNAPSHOTS
VERSION = "v1.4-next-open-verified-3source-display"


def _pair_max_diff(a, b):
    if not a or not b:
        return None
    return verified.max_diff(a, b)


def _stock_api_today(code: str):
    if not os.environ.get("STOCK_API_TOKEN", "").strip():
        return {}
    day = datetime.now(CN).strftime("%Y-%m-%d")
    try:
        from tushare_stock_api import raw_day
        row = raw_day(code, day)
        return {day: row} if row else {}
    except Exception:
        return {}


def fetch_kline_three_source(code: str, limit: int = 620):
    adjusted = verified._original_fetch(code, limit)
    try:
        tx = verified.raw_tencent(code, limit)
    except Exception:
        tx = {}
    try:
        em = verified.raw_eastmoney(code, limit)
    except Exception:
        em = {}
    api = _stock_api_today(code)

    for row in adjusted:
        day = row.get("date")
        candidates = [("Tushare兼容stock_api", api.get(day)), ("腾讯", tx.get(day)), ("东方财富", em.get(day))]
        candidates = [(name, value) for name, value in candidates if value]
        if not candidates:
            continue
        first = candidates[0]
        row["rawOpenVerified"] = legacy.finite(first[1].get("open"))
        row["rawCloseVerified"] = legacy.finite(first[1].get("close"))
        row["rawMaxRelDiff"] = _pair_max_diff(candidates[0][1], candidates[1][1]) if len(candidates) > 1 else None
        row["rawProviders"] = [x[0] for x in candidates]
    return adjusted


def allow_frozen_official(snapshot, now):
    # Audit eligibility controls whether a cohort may enter aggregate strategy statistics;
    # it must not suppress the user's ability to see its factual forward tracking.
    return verified._original_trackable(snapshot, now)


def mark_tracking_use():
    if not SNAPSHOTS.exists():
        return 0
    arr = json.loads(SNAPSHOTS.read_text(encoding="utf-8"))
    changed = 0
    for item in arr:
        if item.get("status") != "Official" or not item.get("trackingUpdatedAt"):
            continue
        audit = item.get("audit") or {}
        use = "Eligible" if audit.get("eligibleForPerformanceComparison") is not False else "ReferenceOnly"
        if item.get("trackingUse") != use:
            item["trackingUse"] = use
            changed += 1
    if changed:
        SNAPSHOTS.write_text(json.dumps(arr, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


legacy.fetch_kline = fetch_kline_three_source
legacy.performance_for = verified.performance_verified
legacy.snapshot_is_trackable = allow_frozen_official
legacy.VERSION = VERSION


def main():
    result = legacy.update_all()
    marked = mark_tracking_use()
    result["trackingUseMarked"] = marked
    result["method"] = VERSION
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
