#!/usr/bin/env python3
"""Tushare-compatible market-data adapter.

Credentials are read from the environment only.  The user-selected proxy is
the primary source; callers may retain their existing public feed as a
documented failover when this adapter is unavailable.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta


DEFAULT_URL = "https://jiaoch.top/"


def configured() -> bool:
    return bool(os.getenv("STOCK_API_TOKEN", "").strip())


def _token() -> str:
    raw = os.getenv("STOCK_API_TOKEN", "").strip()
    candidates = re.findall(r"(?<![0-9a-fA-F])[0-9a-fA-F]{40,128}(?![0-9a-fA-F])", raw)
    token = max(candidates, key=len) if candidates else raw.strip("'\"")
    if not token:
        raise RuntimeError("STOCK_API_TOKEN is not configured")
    return token


def pro_api():
    import tushare as ts

    pro = ts.pro_api(_token())
    pro._DataApi__http_url = os.getenv("STOCK_API_URL", DEFAULT_URL).rstrip("/") + "/"
    return pro


def ts_code(code: str, exchange: str | None = None) -> str:
    code = str(code).split(".")[0]
    if exchange == "sh" or code.startswith(("5", "6")):
        return code + ".SH"
    if exchange == "bj" or code.startswith(("8", "9")):
        return code + ".BJ"
    return code + ".SZ"


def daily_bars(code: str, limit: int = 65, exchange: str | None = None) -> list[dict]:
    """Return ascending, qfq daily bars with provider-reported turnover."""
    import tushare as ts

    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=max(180, limit * 3))).strftime("%Y%m%d")
    asset = "I" if exchange == "sh" and code == "000300" else "E"
    frame = ts.pro_bar(api=pro_api(), ts_code=ts_code(code, exchange),
                       start_date=start, end_date=end, adj=None if asset == "I" else "qfq",
                       asset=asset)
    if frame is None or frame.empty:
        raise RuntimeError("Tushare pro_bar returned no rows")
    rows = []
    for row in frame.head(limit).to_dict("records"):
        # Tushare amount is reported in thousands of yuan.
        amount = row.get("amount")
        rows.append({
            "date": datetime.strptime(str(row["trade_date"]), "%Y%m%d").date().isoformat(),
            "open": _number(row.get("open")), "close": _number(row.get("close")),
            "high": _number(row.get("high")), "low": _number(row.get("low")),
            "amount": _number(amount) * 1000 if _number(amount) is not None else None,
            "source": "Tushare compatible stock_api",
        })
    return sorted(rows, key=lambda x: x["date"])


def raw_day(code: str, day: str) -> dict | None:
    """Return one unadjusted OHLC row for independent close verification."""
    stamp = day.replace("-", "")
    frame = pro_api().daily(ts_code=ts_code(code), start_date=stamp, end_date=stamp)
    if frame is None or frame.empty:
        return None
    row = frame.to_dict("records")[0]
    result = {key: _number(row.get(key)) for key in ("open", "close", "high", "low", "amount")}
    if any(result[key] is None for key in ("open", "close", "high", "low")):
        return None
    if result["amount"] is not None:
        result["amount"] *= 1000
    return result


def realtime_quotes(codes: list[str]) -> dict[str, dict]:
    """Fetch the proxy's Tushare realtime_quote endpoint in bounded batches."""
    out: dict[str, dict] = {}
    pro = pro_api()
    for start in range(0, len(codes), 50):
        batch = [c for c in codes[start:start + 50] if re.fullmatch(r"\d{6}", c or "")]
        if not batch:
            continue
        frame = pro.realtime_quote(ts_code=",".join(ts_code(c) for c in batch))
        if frame is None or frame.empty:
            continue
        for raw in frame.to_dict("records"):
            row = {str(k).lower(): v for k, v in raw.items()}
            code = str(row.get("ts_code") or row.get("code") or "").split(".")[0]
            if not re.fullmatch(r"\d{6}", code):
                continue
            price = _first(row, "price", "close")
            prev = _first(row, "pre_close", "preclose")
            stamp = _quote_stamp(row)
            out[code] = {
                "code": code, "name": row.get("name") or code,
                "quoteOk": bool(price and price > 0),
                "price": price, "prevClose": prev,
                "changePct": ((price / prev - 1) * 100) if price and prev else _first(row, "pct_chg"),
                "quoteTime": stamp, "quoteTimestamp": stamp,
                "amount": _first(row, "amount"), "volumeShares": _first(row, "vol", "volume"),
                "open": _first(row, "open"), "high": _first(row, "high"), "low": _first(row, "low"),
                "source": "Tushare compatible stock_api realtime_quote",
            }
    return out


def _number(value):
    try:
        value = float(value)
        return value if value == value else None
    except (TypeError, ValueError):
        return None


def _first(row, *keys):
    for key in keys:
        value = _number(row.get(key))
        if value is not None:
            return value
    return None


def _quote_stamp(row: dict) -> str | None:
    day = str(row.get("date") or row.get("trade_date") or "").replace("-", "")
    clock = str(row.get("time") or row.get("trade_time") or "").replace(":", "")
    digits = re.sub(r"\D", "", day + clock)
    return digits[:14] if len(digits) >= 14 else None
