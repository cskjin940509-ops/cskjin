#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import update_strategy_backtest as legacy
import update_strategy_backtest_verified_bse  # noqa: F401  patches verified price/bse logic
import update_strategy_backtest_verified as verified

ROOT = Path(__file__).resolve().parents[1]
SNAPS = ROOT / "astock_snapshots" / "index.json"


def trackable_with_reference(snapshot, now):
    audit = snapshot.get("audit") or {}
    status = audit.get("status")
    if snapshot.get("status") != "Official":
        return False
    if audit.get("eligibleForPerformanceComparison") is False:
        # PartiallyVerified cohorts may still have price-path tracking when the
        # next-session entry itself passes the verified raw-price gate. They
        # remain excluded from factor/pool scorecards and comparisons.
        if status == "PartiallyVerified":
            return verified._original_trackable(snapshot, now)
        return False
    return verified._original_trackable(snapshot, now)


legacy.snapshot_is_trackable = trackable_with_reference
legacy.VERSION = "v1.4.1-next-open-verified-reference"


def annotate_reference_only():
    if not SNAPS.exists():
        return 0
    arr = json.loads(SNAPS.read_text(encoding="utf-8"))
    changed = 0
    for item in arr:
        audit = item.get("audit") or {}
        if item.get("status") != "Official" or audit.get("eligibleForPerformanceComparison") is not False:
            continue
        if audit.get("status") != "PartiallyVerified":
            continue
        if not (item.get("stockPerformance") or item.get("poolPerformance")):
            continue
        if item.get("trackingDisplayStatus") != "ReferenceOnly":
            item["trackingDisplayStatus"] = "ReferenceOnly"
            item["trackingDisplayNote"] = "价格路径通过入场价验证后可展示参考跟踪；该批次仍不进入胜率、Alpha或因子有效性统计。"
            changed += 1
    if changed:
        SNAPS.write_text(json.dumps(arr, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


if __name__ == "__main__":
    result = legacy.update_all()
    result["referenceAnnotated"] = annotate_reference_only()
    print(json.dumps(result, ensure_ascii=False))
