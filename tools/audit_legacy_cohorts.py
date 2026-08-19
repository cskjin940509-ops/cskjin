#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

CN = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
SNAPS = ROOT / "astock_snapshots" / "index.json"


def audit_snapshot(item: dict, now: str) -> dict:
    issues: list[str] = []
    pools = item.get("pools") or {}
    stocks = item.get("stocks") or {}
    symbols = sorted({str(c) for values in pools.values() for c in (values or [])})

    if item.get("status") == "Official" and not item.get("strategyVersion"):
        issues.append("missing-strategy-version")
    missing_meta = [code for code in symbols if code not in stocks]
    if missing_meta:
        issues.append(f"missing-stock-metadata:{len(missing_meta)}")
    if pools.get("B1") and not item.get("factorAvailability"):
        issues.append("B1-margin-provenance-missing")
    if pools.get("B2") and not item.get("factorAvailability"):
        issues.append("B2-etf-provenance-missing")
    if symbols and not item.get("dataValidation"):
        issues.append("cross-source-price-validation-missing")

    # Preserve historical membership and legacy status. Audit metadata only controls
    # whether the cohort is eligible for model-performance comparison.
    legacy = bool(issues)
    previous = item.get("audit") or {}
    return {
        "status": "LegacyUnverified" if legacy else "Verified",
        "eligibleForPerformanceComparison": not legacy,
        "issues": issues,
        "auditedAt": now,
        "note": (
            "保留原始冻结名单，不回写/伪造缺失因子；在完成逐项时点审计前不纳入策略胜率、Alpha和池间比较。"
            if legacy else
            "关键冻结元数据与数据校验字段完整。"
        ),
        "previousStatus": previous.get("status"),
    }


def main():
    if not SNAPS.exists():
        raise SystemExit("snapshot index missing")
    arr = json.loads(SNAPS.read_text(encoding="utf-8"))
    now = datetime.now(CN).isoformat(timespec="seconds")
    counts = {"Verified": 0, "LegacyUnverified": 0}
    for item in arr:
        if item.get("status") != "Official":
            continue
        audit = audit_snapshot(item, now)
        item["audit"] = audit
        counts[audit["status"]] += 1
    SNAPS.write_text(json.dumps(arr, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"auditedAt": now, **counts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
