#!/usr/bin/env python3
"""Display-ready verified forward tracking.

Goals:
- Keep the original next-trading-day-open tracking convention.
- Calculate tracking for every frozen Official cohort, even when an older cohort is
  audit-ineligible for leaderboard/model statistics. Such results are marked ReferenceOnly.
- Verify the raw entry-day OHLC with any two agreeing independent providers among
  Tencent, Eastmoney and (for the current session when available) Yunai.
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


def _yunai_today(code: str):
    if not os.environ.get("YUNAI_TOKEN", "").strip() or str(code).startswith(("8", "9")):
        return {}
    day = datetime.now(CN).strftime("%Y-%m-%d")
    try:
        row = daily_verified.yunai_raw_day(code, day)
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
    ya = _yunai_today(code)

    for row in adjusted:
        day = row.get("date")
        candidates = [("腾讯", tx.get(day)), ("东方财富", em.get(day)), ("Yunai", ya.get(day))]
        candidates = [(name, value) for name, value in candidates if value]
        best = None
        for i in range(len(candidates)):
            for j in range(i + 1, len(candidates)):
                diff = _pair_max_diff(candidates[i][1], candidates[j][1])
                if diff is not None and diff <= 0.001 and (best is None or diff < best[0]):
                    best = (diff, candidates[i], candidates[j])
        if best is None:
            continue
        diff, first, second = best
        row["rawOpenVerified"] = legacy.finite(first[1].get("open"))
        row["rawCloseVerified"] = legacy.finite(first[1].get("close"))
        row["rawMaxRelDiff"] = diff
        row["rawProviders"] = [first[0], second[0]]
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
