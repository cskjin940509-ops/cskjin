# -*- coding: utf-8 -*-
"""Per-stock two-financing (margin & securities lending) detail reader.

Source: the Tushare-proxy supplement under ``supplements/tushare/margin_detail``
of the alpha_rank_export. Files are ``margin_detail-YYYYMMDD.json``; each holds
one exchange-published day as ``items`` rows over the field header
``[trade_date, ts_code, rzye, rqye, rzmre, rqyl, rzche, rqchl, rqmcl, rzrqye]``.

Field glossary (yuan unless noted):
    rzye  financing balance        rqye  securities lending balance
    rzmre financing buy amount     rzche financing repayment amount
    rqyl  securities lending qty   rzrqye financing + securities total

The reader normalizes to the cskjin slow-money stock record convention
(6-char bare code, ``balance``/``buyAmount``/``repayAmount``/``netBuyExact``)
so it can sit next to ``astock_factors/latest.json`` margin blocks.

Integrity rules enforced on every read:
- all rows carry the same ``trade_date`` as the filename
- no duplicate ``ts_code`` within a day
- missing values stay ``None`` (never filled with 0; a code absent from the
  day's list simply has no two-financing eligibility record)
- the day's audit status from ``margin-coverage-audit.json`` is surfaced,
  and any pending cross-source reconciliation is reported, not assumed.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .config import data_root
from .mapping import to_bare

_DETAIL_DIR_NAME = "supplements/tushare/margin_detail"
_AUDIT_NAME = "supplements/tushare/margin-coverage-audit.json"

_FIELD_MAP = {
    "rzye": "balance",
    "rzmre": "buyAmount",
    "rzche": "repayAmount",
    "rqye": "secLending",
    "rqyl": "secLendingQty",
    "rqchl": "secLendingRepayQty",
    "rqmcl": "secLendingSellQty",
    "rzrqye": "total",
}


def _base() -> Path:
    root = data_root()
    detail = root / _DETAIL_DIR_NAME
    if not detail.is_dir():
        raise FileNotFoundError(f"margin_detail supplement missing under {root}")
    return root


def available_dates() -> list[str]:
    """YYYYMMDD strings of every available detail day, ascending."""
    base = _base()
    files = list((base / _DETAIL_DIR_NAME).glob("margin_detail-*.json"))
    dates = []
    for f in files:
        m = re.match(r"margin_detail-(\d{8})\.json$", f.name)
        if m:
            dates.append(m.group(1))
    return sorted(set(dates))


def _exchange_of(ts_code: str) -> str:
    suffix = str(ts_code).split(".")[-1].upper()
    return {"SH": "SSE", "SZ": "SZSE", "BJ": "BSE"}.get(suffix, suffix)


def load_day(date: str) -> dict[str, dict]:
    """Read one detail day into ``{bare_code: record}``.

    Record keys: code, ts_code, exchange, balance, buyAmount, repayAmount,
    netBuyExact, secLending, secLendingQty, secLendingRepayQty,
    secLendingSellQty, total, source.
    """
    base = _base()
    compact = str(date).replace("-", "")
    path = base / _DETAIL_DIR_NAME / f"margin_detail-{compact}.json"
    if not path.is_file():
        known = available_dates()
        raise FileNotFoundError(
            f"no margin_detail for {compact}; available: {known}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    fields = payload["fields"]
    idx = {name: i for i, name in enumerate(fields)}
    want = ["trade_date", "ts_code", *_FIELD_MAP]
    missing = [f for f in want if f not in idx]
    if missing:
        raise ValueError(f"{path.name} missing fields {missing}; has {fields}")

    expected_date = compact
    rows: dict[str, dict] = {}
    for raw in payload["items"]:
        row_date = str(raw[idx["trade_date"]])
        if row_date != expected_date:
            raise ValueError(f"{path.name}: row date {row_date} != file date {expected_date}")
        ts_code = str(raw[idx["ts_code"]])
        bare = to_bare(ts_code)
        if bare in rows:
            raise ValueError(f"{path.name}: duplicate code {ts_code}")
        record = {"code": bare, "ts_code": ts_code, "exchange": _exchange_of(ts_code)}
        for src, dst in _FIELD_MAP.items():
            record[dst] = raw[idx[src]]
        buy, repay = record["buyAmount"], record["repayAmount"]
        record["netBuyExact"] = (buy - repay) if buy is not None and repay is not None else None
        record["source"] = "Tushare proxy margin_detail (exchange-published)"
        rows[bare] = record
    return rows


def audit_status() -> dict:
    """Raw day-level audit from margin-coverage-audit.json ({} if absent)."""
    base = _base()
    path = base / _AUDIT_NAME
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def day_audit(date: str) -> dict | None:
    """Audit entry for one day (YYYYMMDD or YYYY-MM-DD)."""
    compact = str(date).replace("-", "")
    return audit_status().get(compact)


def cross_source_reconciled(date: str) -> bool:
    """True only when the audit marks this day past reconciliation."""
    entry = day_audit(date)
    return bool(entry and entry.get("status") == "CROSS_SOURCE_RECONCILED")


def panel(dates: list[str], codes: list[str] | None = None) -> list[dict]:
    """Long panel: one row per (date, code) present in the detail files.

    ``codes`` (6-char or any convention) narrows the output; absent
    combinations are simply not produced (no zero-fill).
    """
    want = {to_bare(c) for c in codes} if codes else None
    out = []
    for d in dates:
        day = load_day(d)
        for bare, rec in day.items():
            if want is None or bare in want:
                out.append({**rec, "date": str(d)[:10] if len(str(d)) >= 10 else d})
    out.sort(key=lambda r: (r["date"], r["code"]))
    return out
