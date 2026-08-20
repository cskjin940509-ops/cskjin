#!/usr/bin/env python3
"""Add Yunai as an independent confirmation layer to the all-day radar.

Important semantic boundary: Yunai largeNetInflow is NOT renamed to Eastmoney
"main force net inflow" and does not silently alter the formation score.  It is kept
as a separate confirmation field so the effect can be evaluated later.
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

import enrich_yunai_gateway as yg
import yunai_tail_overlay as yo

ROOT = Path(__file__).resolve().parents[1]
RADAR = ROOT / "astock_radar" / "latest.json"


def finite(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def main():
    if not RADAR.exists():
        print(json.dumps({"state": "skip", "reason": "radar-missing"}, ensure_ascii=False))
        return
    payload = json.loads(RADAR.read_text(encoding="utf-8"))
    stocks = payload.get("stocks") or {}
    pools = payload.get("pools") or {}
    ordered = []
    for p in ("EarlyEntry", "EarlyWatch", "Confirming", "EstablishedLowChase", "AvoidChase"):
        ordered.extend(pools.get(p) or [])
    ordered.extend(sorted(stocks, key=lambda c: stocks[c].get("earlyEntryScore") or 0.0, reverse=True))
    codes = list(dict.fromkeys(str(c) for c in ordered if c in stocks))[:40]
    if not codes:
        print(json.dumps({"state": "skip", "reason": "no-radar-stocks"}, ensure_ascii=False))
        return

    overlay = yo.fetch_stock_overlay(codes)
    quote_ok = 0
    capital_ok = 0
    for code in codes:
        row = stocks.get(code) or {}
        y = overlay.get(code) or {}
        q = y.get("quote") or {}
        cap = y.get("capital") or {}
        yprice = finite(q.get("price"))
        base_price = finite(row.get("price"))
        diff = None
        if yprice is not None and base_price not in (None, 0):
            diff = yprice / base_price - 1.0
        large = finite(cap.get("largeNetInflow"))
        total = finite(cap.get("totalNetInflow"))
        if y.get("quoteOk"):
            quote_ok += 1
        if y.get("capitalOk"):
            capital_ok += 1
        if large is None:
            confirmation = "NO_CAPITAL_DATA"
        elif large > 0:
            confirmation = "POSITIVE_INDEPENDENT_FLOW"
        elif large < 0:
            confirmation = "NEGATIVE_INDEPENDENT_FLOW"
        else:
            confirmation = "NEUTRAL_INDEPENDENT_FLOW"
        row["yunai"] = {
            "quoteOk": bool(y.get("quoteOk")),
            "capitalOk": bool(y.get("capitalOk")),
            "unsupportedMarket": y.get("unsupportedMarket"),
            "price": yprice,
            "changePct": finite(q.get("changePct")),
            "quoteTime": q.get("latestTime") or q.get("timestamp"),
            "priceVsPrimaryPct": round(diff * 100.0, 4) if diff is not None else None,
            "largeNetInflow": large,
            "totalNetInflow": total,
            "capitalTimestamp": cap.get("retrievedAt") or cap.get("timestamp"),
            "confirmation": confirmation,
            "semanticNote": "largeNetInflow为Yunai独立大单资金分布，不等同东方财富主力净流入",
        }
        stocks[code] = row

    payload["stocks"] = stocks
    payload["yunaiConfirmation"] = {
        "checkedAt": datetime.now(yg.CN).isoformat(timespec="seconds"),
        "provider": "Yunai Quant API",
        "checkedSymbols": codes,
        "quoteAvailable": quote_ok,
        "capitalResponseAvailable": capital_ok,
        "role": "独立确认层；不直接改写formationScore/earlyEntryScore",
    }
    payload["dataSource"] = str(payload.get("dataSource") or "") + " + Yunai独立确认"
    RADAR.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    slot = payload.get("scheduledSlot")
    day = payload.get("date")
    if payload.get("status") == "RadarFinal":
        target = ROOT / "astock_radar" / "history" / f"{day}.json"
    else:
        target = ROOT / "astock_radar" / "intraday" / str(day) / f"{slot}.json"
    if target.exists():
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"state": "radar-yunai-enriched", "symbols": len(codes), "quoteAvailable": quote_ok, "capitalResponseAvailable": capital_ok}, ensure_ascii=False))


if __name__ == "__main__":
    main()
