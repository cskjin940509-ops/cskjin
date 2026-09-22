#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from datetime import datetime

# Importing this module installs BSE-safe market mapping, slow-money stock selection,
# and the compatibility-preserving freeze wrapper.
import run_daily_strategy_verified_bse as bse_compat
import run_daily_strategy_fast as base
import run_daily_strategy_verified as verified

_BASE_VERIFY = verified.verify_price


def _close_time_ok(row: dict | None) -> bool:
    if not row:
        return False
    s = re.sub(r"\D", "", str(row.get("quoteTime") or ""))
    if len(s) >= 6:
        s = s[-6:]
    return len(s) == 6 and s.isdigit() and int(s) >= 145900


def verify_price_resilient(code: str, day: str) -> dict:
    """Accept one approved provider; use same-day close snapshot as a fallback."""
    first = _BASE_VERIFY(code, day)
    if first.get("verified"):
        return first

    checks = list(first.get("checks") or [])
    valid: list[tuple[str, str, dict]] = []

    try:
        tx = bse_compat.tencent_same_day_snapshot(code, day)
        if tx and not _close_time_ok(tx):
            checks.append({"provider": "腾讯同日收盘快照", "row": tx, "error": "quote-before-14:59"})
            tx = None
        else:
            checks.append({"provider": "腾讯同日收盘快照", "row": tx})
        if tx and all(verified.finite(tx.get(k)) is not None for k in ("open", "close", "high", "low")):
            valid.append(("腾讯同日收盘快照", "Tencent", tx))
    except Exception as e:
        checks.append({"provider": "腾讯同日收盘快照", "row": None, "error": e.__class__.__name__})

    try:
        em = verified.eastmoney_raw_day(code, day)
        checks.append({"provider": "东方财富未复权日线", "row": em})
        if em and all(verified.finite(em.get(k)) is not None for k in ("open", "close", "high", "low")):
            valid.append(("东方财富未复权日线", "Eastmoney", em))
    except Exception as e:
        checks.append({"provider": "东方财富未复权日线", "row": None, "error": e.__class__.__name__})

    if valid:
        a = valid[0]
        return {
            "verified": True,
            "rawClose": verified.finite(a[2].get("close")),
            "maxRelDiff": None,
            "providers": [x[0] for x in valid],
            "selectedProvider": a[0],
            "checks": checks,
            "rule": "任一合规源成功即放行；多源仅作诊断",
            "fallbackUsed": True,
        }

    first["checks"] = checks
    first["fallbackUsed"] = True
    return first


verified.verify_price = verify_price_resilient


def main() -> int:
    requested = os.getenv("TARGET_DATE", "").strip()
    if requested:
        day = requested
    else:
        latest = json.loads((verified.GATEWAY / "latest.json").read_text(encoding="utf-8"))
        day = (latest.get("marketSnapshot") or {}).get("sourceDate")
    if not day:
        raise RuntimeError("无法确定目标交易日")

    verified.TARGET_DAY = day
    prior = verified.existing_official(day)
    if prior and os.getenv("FORCE_REBUILD", "0") != "1":
        print(json.dumps({"state": "immutable", "date": day, "reason": "Official cohort already exists"}, ensure_ascii=False))
        return 0

    payload = verified.load_frozen_payload(day)
    now = datetime.now(verified.CN)
    target = datetime.strptime(day, "%Y-%m-%d").date()
    if now.date() != target:
        raise RuntimeError("历史重建缺少 point-in-time 成分股快照；禁止生成 Official")

    base.kline = verified.safe_kline
    base.VERSION = verified.VERSION
    selected = base.choose_sectors(payload)
    stocks, pools = base.choose_stocks(selected)

    required = sorted({str(c) for values in pools.values() for c in (values or [])})
    validations = {code: verified.verify_price(code, day) for code in required}
    failed = [code for code, v in validations.items() if not v.get("verified")]
    valid = [code for code in required if code not in failed]

    print(json.dumps({
        "validationSummary": {
            "requested": len(required),
            "verified": len(valid),
            "failed": failed,
            "fallbackVerified": [c for c in valid if validations[c].get("fallbackUsed")],
        }
    }, ensure_ascii=False))

    if required and not valid:
        raise RuntimeError("全部入池股票均无合规行情源，禁止生成 Official")
    # Isolated provider failures must not erase an otherwise verified trading day,
    # but broad validation degradation still blocks the cohort.
    max_exclusions = max(3, int(len(required) * 0.20)) if required else 0
    if len(failed) > max_exclusions:
        raise RuntimeError(
            f"行情源大面积异常：{len(failed)}/{len(required)}只失败，超过允许隔离阈值{max_exclusions}只"
        )

    valid_set = set(valid)
    filtered_pools = {
        name: [str(code) for code in (members or []) if str(code) in valid_set]
        for name, members in pools.items()
    }
    filtered_stocks = [s for s in stocks if str(s.get("code")) in valid_set]

    by_code = {str(s["code"]): s for s in filtered_stocks}
    for code in valid:
        v = validations[code]
        if code in by_code:
            by_code[code]["price"] = v["rawClose"]
            by_code[code]["priceValidation"] = {
                k: v.get(k) for k in ("verified", "maxRelDiff", "providers", "rule", "fallbackUsed")
            }

    base.freeze(day, payload, selected, filtered_stocks, filtered_pools)
    arr = json.loads(verified.SNAPS.read_text(encoding="utf-8"))
    used_providers = sorted({p for code in valid for p in (validations[code].get("providers") or [])})
    excluded = []
    for code in failed:
        v = validations[code]
        excluded.append({
            "code": code,
            "reason": v.get("reason") or "无合规行情源返回未复权OHLC",
            "maxRelDiff": v.get("maxRelDiff") or v.get("bestMaxRelDiff"),
            "checks": v.get("checks") or [],
        })

    for item in arr:
        if item.get("date") != day:
            continue
        item["strategyVersion"] = verified.VERSION
        item["dataValidation"] = {
            "status": "VerifiedWithExclusions" if failed else "Verified",
            "priceBasis": "未复权实际收盘价",
            "factorPriceBasis": "前复权，仅用于RS/MTA等因子",
            "factorBarsCutoff": day,
            "priceProviders": used_providers,
            "requestedStockCount": len(required),
            "stockCount": len(valid),
            "excludedStockCount": len(failed),
            "excludedStocks": excluded,
            "fallbackVerifiedStocks": [c for c in valid if validations[c].get("fallbackUsed")],
            "rule": "Tushare/同花顺/腾讯/东方财富任一合规源成功即放行；孤立失败股票剔除。",
        }
        item["audit"] = {
            "status": "VerifiedWithExclusions" if failed else "Verified",
            "eligibleForPerformanceComparison": True,
            "issues": [f"{x['code']}因所有合规行情源失败已从当日正式池剔除" for x in excluded],
            "auditedAt": datetime.now(verified.CN).isoformat(timespec="seconds"),
            "note": "生产扫描通过目标日时点门禁；任一合规行情源成功即可进入Official。",
        }
        for code in valid:
            v = validations[code]
            meta = (item.get("stocks") or {}).get(code)
            if meta is not None:
                meta["selectionPrice"] = v["rawClose"]
                meta["priceValidation"] = {
                    "status": "Verified",
                    "providers": v.get("providers") or [],
                    "maxRelDiff": v.get("maxRelDiff"),
                    "basis": "raw-close",
                    "fallbackUsed": bool(v.get("fallbackUsed")),
                }
        break

    verified.SNAPS.write_text(json.dumps(arr, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "state": "verified-official",
        "date": day,
        "stocks": len(valid),
        "excluded": failed,
        "version": verified.VERSION,
        "providers": used_providers,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
