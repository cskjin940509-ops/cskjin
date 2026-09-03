#!/usr/bin/env python3
"""Fail fast when a production payload disappears or changes shape."""

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.request import Request, urlopen

BASES = (
    "https://raw.githubusercontent.com/cskjin940509-ops/cskjin/main/",
    "https://github.com/cskjin940509-ops/cskjin/raw/refs/heads/main/",
)

CONTRACTS = {
    "astock_gateway/latest.json": (dict, ("generatedAt", "state", "marketSnapshot", "boardHeatmap", "quotes")),
    "astock_snapshots/index.json": (list, ()),
    "astock_radar/latest.json": (dict, ("date", "capturedAt", "status", "mainlines", "stocks")),
    "astock_trade/latest.json": (dict, ("date", "generatedAt", "officialPlans", "setupCandidates")),
    "astock_execution/latest.json": (dict, ("date", "generatedAt", "stocks", "ranking")),
    "astock_tail/latest.json": (dict, ("date", "capturedAt", "status", "stocks")),
    "astock_ai_portfolio/latest.json": (dict, ("updatedAt", "summary", "positions", "targetPortfolio")),
    "astock_ai_portfolio/ledger.json": (list, ()),
    "astock_factors/latest.json": (dict, ("dataDate", "margin", "etf", "provenance")),
    "astock_premarket/latest.json": (dict, ("generatedAt", "targetDate", "state", "candidates")),
    "astock_history/latest.json": (dict, ("updatedAt", "overall", "conditions")),
}


def fetch(path: str):
    last = None
    for base in BASES:
        try:
            req = Request(base + path, headers={"User-Agent": "AStockStrategy-contract/4.1", "Cache-Control": "no-cache"})
            with urlopen(req, timeout=20) as response:
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(f"HTTP {response.status}")
                body = response.read(30 * 1024 * 1024)
            return json.loads(body.decode("utf-8")), len(body)
        except Exception as exc:
            last = exc
    raise RuntimeError(str(last or "all endpoints failed"))


def main() -> int:
    failures = []
    results = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        pending = {executor.submit(fetch, path): path for path in CONTRACTS}
        for future in as_completed(pending):
            path = pending[future]
            try:
                results[path] = future.result()
            except Exception as exc:
                results[path] = exc

    for path, (expected_type, keys) in CONTRACTS.items():
        try:
            result = results[path]
            if isinstance(result, Exception):
                raise result
            payload, size = result
            if not isinstance(payload, expected_type):
                raise TypeError(f"expected {expected_type.__name__}, got {type(payload).__name__}")
            if isinstance(payload, list) and not payload:
                raise ValueError("empty snapshot list")
            missing = [key for key in keys if key not in payload]
            if missing:
                raise KeyError("missing keys: " + ", ".join(missing))
            marker = None
            if isinstance(payload, dict):
                marker = next((payload.get(k) for k in ("generatedAt", "updatedAt", "capturedAt", "dataDate", "date") if payload.get(k)), None)
            print(json.dumps({"path": path, "ok": True, "bytes": size, "serverTime": marker}, ensure_ascii=False))
        except Exception as exc:
            failures.append(f"{path}: {exc}")
            print(json.dumps({"path": path, "ok": False, "error": str(exc)}, ensure_ascii=False))

    print(json.dumps({
        "checkedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "contracts": len(CONTRACTS),
        "failures": failures,
    }, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
