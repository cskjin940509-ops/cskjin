#!/usr/bin/env python3
"""Re-verify legacy Official cohorts without rewriting their historical membership.

This script separates three questions:
1) Can raw market facts/prices be independently rechecked now?
2) Can factor inputs be recomputed with bars capped at the historical signal date?
3) Is there enough point-in-time evidence to prove that the ORIGINAL historical
   selection was reproducible at that time?

Only (3) can promote a legacy cohort to fully Verified. Recomputed data is stored
as audit evidence and never silently substituted for missing original provenance.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import run_daily_strategy_fast as base
import run_daily_strategy_verified as verified
from bse_market_mapping import eastmoney_secid, tencent_symbol

CN = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
SNAPS = ROOT / "astock_snapshots" / "index.json"
HISTORY = ROOT / "astock_gateway" / "history"
REPORT_DIR = ROOT / "astock_gateway" / "validation"


def finite(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def all_symbols(item: dict) -> list[str]:
    return sorted({
        str(code)
        for values in (item.get("pools") or {}).values()
        for code in (values or [])
        if str(code).isdigit()
    })


def frozen_market_evidence(day: str) -> dict:
    p = HISTORY / f"{day}.json"
    if not p.exists():
        return {"available": False, "reason": "frozen-market-snapshot-missing"}
    try:
        o = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"available": False, "reason": f"invalid-frozen-market:{e.__class__.__name__}"}
    market = o.get("marketSnapshot") or {}
    heat = o.get("boardHeatmap") or {}
    same_day = market.get("sourceDate") == day
    boards = len(heat.get("industry") or []) + len(heat.get("concept") or [])
    return {
        "available": bool(same_day and boards),
        "sourceDate": market.get("sourceDate"),
        "availableAt": market.get("availableAt"),
        "boardCount": boards,
        "sameDay": same_day,
    }


def patch_market_mappings(day: str):
    verified.symbol = lambda code: tencent_symbol(str(code))
    verified.secid = lambda code: eastmoney_secid(str(code))
    verified.TARGET_DAY = day
    base.sid = lambda code: eastmoney_secid(str(code))


def price_audit(day: str, codes: list[str]) -> dict:
    patch_market_mappings(day)
    rows = {}
    ok = 0
    bse_single_source = 0
    for code in codes:
        try:
            result = verified.verify_price(code, day)
        except Exception as e:
            result = {"verified": False, "reason": f"audit-error:{e.__class__.__name__}", "checks": []}
        checks = result.get("checks") or []
        providers = [x.get("provider") for x in checks if x.get("row")]
        if result.get("verified"):
            ok += 1
        elif code.startswith(("8", "9")) and "东方财富" in providers:
            # Tencent live supports BSE but its historical fqkline endpoint can return
            # no day row for 920xxx. Do not weaken the two-source rule; record coverage.
            bse_single_source += 1
        rows[code] = {
            "verified": bool(result.get("verified")),
            "rawClose": result.get("rawClose"),
            "maxRelDiff": result.get("maxRelDiff"),
            "reason": result.get("reason"),
            "providersWithRow": providers,
        }
    total = len(codes)
    return {
        "total": total,
        "verified": ok,
        "coveragePct": round(100.0 * ok / total, 2) if total else 100.0,
        "bseSingleSource": bse_single_source,
        "rule": "signal-day raw OHLC must agree across two independent providers within 0.1%",
        "stocks": rows,
    }


def factor_recompute(day: str, codes: list[str]) -> dict:
    patch_market_mappings(day)
    out = {}
    ok = 0
    for code in codes:
        try:
            bars = verified.safe_kline(eastmoney_secid(code), 90)
            h = base.trend(bars)
            available = len(bars) >= 21
            if available:
                ok += 1
            out[code] = {
                "available": available,
                "barCount": len(bars),
                "lastBarDate": bars[-1]["date"] if bars else None,
                "r20": h.get("r20"),
                "r60": h.get("r60"),
                "mta": h.get("mta"),
            }
        except Exception as e:
            out[code] = {"available": False, "error": e.__class__.__name__}
    return {
        "available": ok,
        "total": len(codes),
        "coveragePct": round(100.0 * ok / len(codes), 2) if codes else 100.0,
        "cutoff": day,
        "methodology": "current safe qfq factor recomputation capped at historical date; evidence only, not original-factor substitution",
        "stocks": out,
    }


def factor_provenance(item: dict) -> dict:
    pools = item.get("pools") or {}
    availability = item.get("factorAvailability") or {}
    stocks = item.get("stocks") or {}
    checks = {}

    # B0 requires original strategy/version + stock metadata to reproduce original ranking.
    checks["B0"] = {
        "used": bool(pools.get("B0")),
        "proven": bool(item.get("strategyVersion") and stocks),
        "evidence": "strategyVersion+stockMetadata" if item.get("strategyVersion") and stocks else None,
    }
    # B1/B2 cannot be reconstructed from price bars; require original source provenance.
    for pool, key in (("B1", "margin"), ("B2", "etf")):
        used = bool(pools.get(pool))
        text = str(availability.get(pool) or "")
        checks[pool] = {
            "used": used,
            "proven": (not used) or bool(text and "未同步" not in text and "留空" not in text),
            "evidence": text or None,
            "requiredSource": key,
        }
    # B3 can at least be tied to frozen per-stock money-flow fields when metadata exists.
    b3_codes = [str(x) for x in pools.get("B3") or []]
    b3_meta = [stocks.get(c) or {} for c in b3_codes]
    b3_has_fields = bool(b3_codes) and all(
        finite(x.get("mainNetFlow")) is not None or finite(x.get("mainFlowPct")) is not None
        for x in b3_meta
    )
    checks["B3"] = {
        "used": bool(b3_codes),
        "proven": (not b3_codes) or b3_has_fields,
        "evidence": "frozen-stock-main-flow-fields" if b3_has_fields else None,
    }
    used_checks = [v for v in checks.values() if v.get("used")]
    return {
        "complete": all(v.get("proven") for v in used_checks) if used_checks else True,
        "checks": checks,
    }


def point_in_time_membership(item: dict) -> dict:
    # Historical board membership must be explicitly frozen. Current constituents,
    # or merely having a `sector` label on a stock, are insufficient evidence.
    candidates = [
        item.get("pointInTimeConstituents"),
        item.get("constituentSnapshot"),
        item.get("boardMembershipSnapshot"),
    ]
    available = any(bool(x) for x in candidates)
    return {
        "available": available,
        "rule": "must have a frozen historical constituent/membership snapshot; current membership is not accepted",
    }


def audit_one(item: dict, now: str) -> tuple[dict, dict]:
    day = item.get("date")
    codes = all_symbols(item)
    stocks = item.get("stocks") or {}
    missing_meta = [c for c in codes if c not in stocks]
    market = frozen_market_evidence(day)
    prices = price_audit(day, codes)
    factors = factor_recompute(day, codes)
    provenance = factor_provenance(item)
    membership = point_in_time_membership(item)

    issues = []
    if not item.get("strategyVersion"):
        issues.append("missing-original-strategy-version")
    if missing_meta:
        issues.append(f"missing-original-stock-metadata:{len(missing_meta)}")
    if not market.get("available"):
        issues.append("same-day-frozen-market-snapshot-missing")
    if prices.get("verified") != prices.get("total"):
        issues.append(f"raw-price-cross-source-incomplete:{prices.get('verified')}/{prices.get('total')}")
    if not provenance.get("complete"):
        issues.append("original-factor-provenance-incomplete")
    if not membership.get("available"):
        issues.append("point-in-time-constituent-snapshot-missing")

    fully_reproducible = not issues
    meaningful_recheck = (
        prices.get("verified", 0) > 0
        or factors.get("available", 0) > 0
        or market.get("available")
    )
    status = "Verified" if fully_reproducible else ("PartiallyVerified" if meaningful_recheck else "LegacyUnverified")

    audit = {
        "status": status,
        "eligibleForPerformanceComparison": status == "Verified",
        "issues": issues,
        "auditedAt": now,
        "note": (
            "旧批次已完成可恢复数据的逐项复核；只有原始时点成分、因子来源和双源价格全部可证明时才升级为 Verified。"
        ),
        "reverification": {
            "rawPrice": {k: v for k, v in prices.items() if k != "stocks"},
            "factorRecompute": {k: v for k, v in factors.items() if k != "stocks"},
            "frozenMarket": market,
            "factorProvenance": provenance,
            "pointInTimeMembership": membership,
            "originalMetadata": {
                "strategyVersion": item.get("strategyVersion"),
                "symbols": len(codes),
                "stockMetadataPresent": len(codes) - len(missing_meta),
                "stockMetadataMissing": len(missing_meta),
            },
        },
    }
    report = {
        "date": day,
        "status": status,
        "fullyReproducible": fully_reproducible,
        "eligibleForPerformanceComparison": status == "Verified",
        "issues": issues,
        "rawPrice": prices,
        "factorRecompute": factors,
        "frozenMarket": market,
        "factorProvenance": provenance,
        "pointInTimeMembership": membership,
        "auditedAt": now,
    }
    return audit, report


def main():
    if not SNAPS.exists():
        raise SystemExit("snapshot index missing")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    arr = json.loads(SNAPS.read_text(encoding="utf-8"))
    now = datetime.now(CN).isoformat(timespec="seconds")
    summary = {"Verified": 0, "PartiallyVerified": 0, "LegacyUnverified": 0}
    reports = []

    for item in arr:
        if item.get("status") != "Official":
            continue
        if (item.get("audit") or {}).get("status") == "Verified":
            summary["Verified"] += 1
            continue
        audit, report = audit_one(item, now)
        item["audit"] = audit
        summary[audit["status"]] += 1
        reports.append(report)
        (REPORT_DIR / f"legacy-{item.get('date')}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    SNAPS.write_text(json.dumps(arr, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (REPORT_DIR / "legacy-summary.json").write_text(
        json.dumps({"auditedAt": now, "summary": summary, "reports": [
            {k: r.get(k) for k in ("date", "status", "fullyReproducible", "eligibleForPerformanceComparison", "issues")}
            for r in reports
        ]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"auditedAt": now, **summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
