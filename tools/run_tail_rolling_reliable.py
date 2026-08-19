#!/usr/bin/env python3
"""Reliable wrapper for the rolling tail decision.

Why this exists:
- During market hours, a quote older than 8 minutes is genuinely stale.
- After 15:00, the exchange is closed: a same-day closing quote timestamp around
  15:00 is still the correct final market fact even if the workflow starts later.
- GitHub scheduled jobs can start late, so a missing TailFinal must remain
  recoverable for the rest of the trading day instead of being permanently lost.

The underlying selection logic and persistence semantics remain in
run_tail_rolling.py / run_tail_decision.py. This wrapper only changes the
post-close freshness interpretation and optionally runs in FINAL_ONLY mode.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, time as dtime

import run_tail_rolling as rolling

CN = rolling.CN

_original_build_payload = rolling.core.build_payload


def build_payload_market_aware(now: datetime):
    # Before the close keep the original strict point-in-time freshness gate.
    if now.time() < dtime(15, 0):
        return _original_build_payload(now)

    core = rolling.core
    core.USED_DELAYED = False
    quotes, provider_date = core.current_index_payload()
    today_compact = now.strftime("%Y%m%d")
    if provider_date != today_compact:
        raise RuntimeError(f"腾讯指数行情日期不是今天: {provider_date}")

    stamps = []
    for x in quotes.values():
        raw = x.get("quoteTimeRaw")
        if raw and len(raw) >= 14 and raw[:14].isdigit():
            try:
                stamps.append(datetime.strptime(raw[:14], "%Y%m%d%H%M%S").replace(tzinfo=CN))
            except Exception:
                pass
    max_stamp = max(stamps) if stamps else None
    if max_stamp is None:
        raise RuntimeError("收盘指数行情缺少时间戳")
    if max_stamp.date() != now.date() or max_stamp.time() < dtime(14, 55):
        raise RuntimeError(f"未取得当日有效收盘附近指数快照: {max_stamp.isoformat()}")

    industry = core.tail_boards("industry")
    concept = core.tail_boards("concept")
    if not industry:
        raise RuntimeError("行业板块为空")

    payload = {
        "marketSnapshot": {
            "sourceDate": now.strftime("%Y-%m-%d"),
            "availableAt": now.isoformat(timespec="seconds"),
            "verifiedToday": True,
            "indices": core.gw.index_snapshot(quotes),
        },
        "boardHeatmap": {
            "industry": industry,
            "concept": concept,
            "sourceDate": now.strftime("%Y-%m-%d"),
            "availableAt": now.isoformat(timespec="seconds"),
        },
    }
    quote_age = max(0.0, (now - max_stamp).total_seconds())
    return payload, quote_age


def main():
    now = datetime.now(CN)
    final_only = os.getenv("FINAL_ONLY", "0") == "1"
    if final_only and now.time() < dtime(15, 0):
        print(json.dumps({
            "state": "skip",
            "reason": "final-only-before-close",
            "capturedAt": now.isoformat(timespec="seconds"),
        }, ensure_ascii=False))
        return

    # After the close, allow recovery at any later same-day invocation. The
    # market-aware build_payload still requires a same-day closing snapshot.
    if now.time() >= dtime(15, 0):
        os.environ["ALLOW_ANY_TIME"] = "1"
        rolling.core.build_payload = build_payload_market_aware

    rolling.main()


if __name__ == "__main__":
    main()
