#!/usr/bin/env python3
"""Backfill 485 point-in-time ETF share cross-sections from the configured proxy.

The credential is read only from STOCK_API_TOKEN and is never persisted or logged.
Files are written per trade date so interrupted runs resume without refetching.
"""
from __future__ import annotations

import gzip
import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKFILL = ROOT / "astock_factors" / "proxy_backfill"
OUT = BACKFILL / "etf_share_daily"
API_URL = os.getenv("STOCK_API_URL", "https://jiaoch.top/")
TOKEN = os.getenv("STOCK_API_TOKEN", "").strip()
WINDOW = 485
WORKERS = max(1, min(int(os.getenv("ETF_BACKFILL_WORKERS", "6")), 12))


def request(api_name, params):
    body = json.dumps({"api_name": api_name, "token": TOKEN,
                       "params": params, "fields": ""}).encode()
    req = urllib.request.Request(API_URL, data=body, headers={
        "Content-Type": "application/json", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=50) as response:
        raw = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    payload = json.loads(raw)
    if payload.get("code") != 0:
        raise RuntimeError(f"proxy code {payload.get('code')}")
    return payload.get("data") or {}


def trading_dates():
    try:
        payload = json.loads((BACKFILL / "margin.json").read_text(encoding="utf-8"))
        data = payload.get("data") or {}
    except (OSError, ValueError):
        # GitHub may check out large historical files as LFS pointers.  Resolve
        # the calendar from the API itself instead of depending on that file.
        calendar = request("trade_cal", {"exchange": "SSE",
                                         "start_date": "20240901",
                                         "end_date": datetime.now().strftime("%Y%m%d"),
                                         "is_open": "1", "limit": 2000})
        fields = calendar.get("fields") or []
        di = fields.index("cal_date")
        dates = sorted({str(row[di]) for row in calendar.get("items") or []})
        return dates[-(WINDOW + 1):]
    fields = data.get("fields") or []
    di, ei = fields.index("trade_date"), fields.index("exchange_id")
    coverage = {}
    for row in data.get("items") or []:
        if str(row[ei]) in ("SSE", "SZSE"):
            coverage.setdefault(str(row[di]), set()).add(str(row[ei]))
    dates = sorted(d for d, exchanges in coverage.items()
                   if exchanges == {"SSE", "SZSE"})
    # Need one predecessor to calculate the first daily share change.
    return dates[-(WINDOW + 1):]


def valid_existing(path, expected_date):
    try:
        x = json.loads(path.read_text(encoding="utf-8")); d = x["data"]
        fields, rows = d["fields"], d["items"]
        di = fields.index("trade_date")
        return len(rows) > 100 and all(str(r[di]) == expected_date for r in rows)
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return False


def fetch_day(day):
    path = OUT / f"{day}.json"
    if valid_existing(path, day):
        return day, "cached", None
    last = None
    for attempt in range(4):
        try:
            data = request("fund_share", {"trade_date": day, "limit": 6000})
            fields, rows = data.get("fields") or [], data.get("items") or []
            if "trade_date" not in fields or "ts_code" not in fields or "fd_share" not in fields:
                raise ValueError("required fund_share fields missing")
            di = fields.index("trade_date")
            if len(rows) <= 100 or any(str(r[di]) != day for r in rows):
                raise ValueError("empty, truncated, or wrong-date ETF cross-section")
            payload = {"source": API_URL, "classification": "THIRD_PARTY_SOURCE_RAW",
                       "retrievedAt": datetime.now(timezone.utc).isoformat(),
                       "api": "fund_share", "requestedTradeDate": day, "data": data}
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
            return day, "downloaded", None
        except Exception as error:
            last = error
            time.sleep(1.5 * (attempt + 1))
    return day, "failed", type(last).__name__


def main():
    if not TOKEN:
        raise SystemExit("STOCK_API_TOKEN is required")
    OUT.mkdir(parents=True, exist_ok=True)
    dates = trading_dates()
    if len(dates) < WINDOW + 1:
        raise SystemExit(f"only {len(dates)} complete trading dates")
    counts = {"cached": 0, "downloaded": 0, "failed": 0}; failures = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(fetch_day, day) for day in dates]
        for future in as_completed(futures):
            day, status, error = future.result(); counts[status] += 1
            if error: failures.append({"tradeDate": day, "errorType": error})
            done = sum(counts.values())
            if done % 25 == 0:
                print(json.dumps({"completed": done, "requested": len(dates), **counts}))
    manifest = {"generatedAt": datetime.now(timezone.utc).isoformat(),
                "requiredTradingDays": WINDOW, "requestedSnapshots": len(dates),
                "workers": WORKERS, **counts, "failures": failures,
                "complete": counts["failed"] == 0 and len(dates) >= WINDOW + 1}
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    if not manifest["complete"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
