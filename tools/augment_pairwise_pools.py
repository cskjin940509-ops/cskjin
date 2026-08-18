#!/usr/bin/env python3
"""Add pairwise confirmation pools to the just-frozen Daily Cohort.

B12 = B1(two-margin) + B2(ETF)
B13 = B1(two-margin) + B3(main-flow)
B23 = B2(ETF) + B3(main-flow)

Eligibility requires that the stock is already confirmed by both source pools.
Within the eligible set we re-rank by the frozen base score and any numeric
factor scores that are actually present. Missing numeric factor scores are NOT
imputed; in that case the frozen base score is used only to order already-
confirmed members. If either source pool has no members, the combo pool stays
empty. Historical cohorts are not backfilled by this script; it only touches
the requested/current cohort during the same daily freeze run.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPS = ROOT / "astock_snapshots" / "index.json"
PAIR_DEFS = {
    "B12": ("B1", "B2", "两融+ETF"),
    "B13": ("B1", "B3", "两融+主力"),
    "B23": ("B2", "B3", "ETF+主力"),
}


def finite(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def factor_score(meta: dict, pool: str):
    keys = {
        "B1": ("marginScore", "marginFactorScore", "twoMarginScore"),
        "B2": ("etfScore", "etfFlowScore", "etfFactorScore"),
        "B3": ("mainFlowScore", "flowScore", "mfiScore"),
    }[pool]
    for key in keys:
        value = finite(meta.get(key))
        if value is not None:
            return value
    return None


def combo_score(meta: dict, left: str, right: str):
    base = finite(meta.get("score"))
    l = factor_score(meta, left)
    r = factor_score(meta, right)
    if base is None:
        base = 50.0
    # Preferred formula when actual numeric factor strengths exist.
    if l is not None and r is not None:
        return 0.55 * base + 0.225 * l + 0.225 * r, "55%基础+22.5%+22.5%资金因子"
    # Do not invent missing factor scores. Membership already proves both
    # factor screens passed, so base score is used only for ordering.
    return base, "双因子已确认；缺数值因子时仅按基础强度重排"


def main():
    if not SNAPS.exists():
        raise SystemExit("snapshot index missing")
    arr = json.loads(SNAPS.read_text(encoding="utf-8"))
    target = os.environ.get("TARGET_DATE") or ""
    if not target:
        official = [x for x in arr if x.get("status") == "Official"]
        if not official:
            raise SystemExit("no Official cohort")
        target = max(official, key=lambda x: x.get("date", "")).get("date")
    item = next((x for x in arr if x.get("date") == target), None)
    if item is None:
        raise SystemExit(f"cohort {target} missing")

    pools = item.setdefault("pools", {})
    stocks = item.get("stocks") or {}
    combo_meta = item.setdefault("comboPools", {})

    for combo, (left, right, label) in PAIR_DEFS.items():
        left_set = set(pools.get(left) or [])
        right_set = set(pools.get(right) or [])
        eligible = left_set & right_set
        ranked = []
        methods = set()
        for code in eligible:
            meta = stocks.get(code) or {}
            score, method = combo_score(meta, left, right)
            methods.add(method)
            ranked.append((score, code))
        ranked.sort(key=lambda x: (-x[0], x[1]))
        selected = [code for _, code in ranked[:10]]
        pools[combo] = selected
        combo_meta[combo] = {
            "label": label,
            "sources": [left, right],
            "members": len(selected),
            "method": "；".join(sorted(methods)) if methods else "必要源池缺失/无共同达标股票，保持为空",
            "requires": "两个源因子均有正式入池确认",
        }
        for code in selected:
            meta = stocks.get(code)
            if isinstance(meta, dict):
                ps = list(meta.get("pools") or [])
                if combo not in ps:
                    ps.append(combo)
                meta["pools"] = ps

    availability = item.setdefault("factorAvailability", {})
    availability.update({
        "B12": "两融+ETF；任一源池缺失则为空",
        "B13": "两融+主力；任一源池缺失则为空",
        "B23": "ETF+主力；任一源池缺失则为空",
    })
    item["poolSchemaVersion"] = "v2-pairwise"
    SNAPS.write_text(json.dumps(arr, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"date": target, **{k: pools.get(k, []) for k in PAIR_DEFS}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
