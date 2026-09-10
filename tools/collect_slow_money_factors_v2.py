#!/usr/bin/env python3
"""Robust wrapper for slow-money collection.

Adds SZSE retry/backoff, BSE margin detail, and a separately labelled
whole-market financing-balance input for the original sentiment research.
ETF collection remains exchange-share based.
"""
from __future__ import annotations

import time
import akshare as ak
import collect_slow_money_factors as base

_original_fetch_margin_day = base.fetch_margin_day
_original_collect_margin = base.collect_margin


def _merge_margin_df(merged, df, exchange, source):
    for r in base.df_records(df):
        code = base.code6(r.get("证券代码"))
        if not code:
            continue
        bal = base.finite(r.get("融资余额"))
        buy = base.finite(r.get("融资买入额"))
        merged[code] = {
            "code": code,
            "name": r.get("证券简称"),
            "balance": bal,
            "buyAmount": buy,
            "repayAmount": None,
            "netBuyExact": None,
            "source": source,
            "exchange": exchange,
        }


def fetch_margin_day_v2(d):
    day, merged, errors = _original_fetch_margin_day(d)
    stamp = base.ds(d)

    if "SZSE" in errors:
        last = None
        for attempt in range(3):
            try:
                df = ak.stock_margin_detail_szse(date=stamp)
                _merge_margin_df(merged, df, "SZSE", "深交所融资融券明细")
                errors.pop("SZSE", None)
                break
            except Exception as e:
                last = e
                time.sleep(1.5 * (attempt + 1))
        if "SZSE" in errors and last is not None:
            errors["SZSE"] = f"{last.__class__.__name__}:三次重试仍失败"

    try:
        df = ak.stock_margin_detail_bse(date=stamp)
        _merge_margin_df(merged, df, "BSE", "北交所融资融券明细")
        errors.pop("BSE", None)
    except Exception as e:
        errors["BSE"] = e.__class__.__name__

    return day, merged, errors


def _first_finite(records, names):
    for row in records:
        for name in names:
            value = base.finite(row.get(name))
            if value is not None:
                return value
    return None


def fetch_market_margin_summary(d):
    """Fetch exchange totals without pretending a partial sum is complete.

    SSE publishes a historical summary table; SZSE exposes a one-day summary.
    AKShare currently has no consistently documented BSE summary call, so the
    BSE balance is summed from that day's official detail when available.
    """
    stamp = base.ds(d)
    balances, errors, sources = {}, {}, {}
    try:
        df = ak.stock_margin_sse(start_date=stamp, end_date=stamp)
        value = _first_finite(base.df_records(df), ("融资余额", "融资余额(元)"))
        if value is None:
            raise ValueError("missing financing balance")
        balances["SSE"] = value
        sources["SSE"] = "上交所融资融券汇总"
    except Exception as e:
        errors["SSE"] = e.__class__.__name__
    try:
        df = ak.stock_margin_szse(date=stamp)
        value = _first_finite(base.df_records(df), ("融资余额", "融资余额(元)"))
        if value is None:
            raise ValueError("missing financing balance")
        # The documented SZSE wrapper uses 亿元; tolerate an explicit 元 field.
        if value < 1e7:
            value *= 1e8
        balances["SZSE"] = value
        sources["SZSE"] = "深交所融资融券汇总"
    except Exception as summary_error:
        # The SZSE summary endpoint occasionally changes its JSON shape. The
        # official per-security table carries the same balance field, so use
        # its exact daily sum instead of discarding the whole exchange.
        try:
            df = ak.stock_margin_detail_szse(date=stamp)
            values = [base.finite(x.get("融资余额")) for x in base.df_records(df)]
            values = [x for x in values if x is not None]
            if not values:
                raise ValueError("missing financing balance")
            balances["SZSE"] = sum(values)
            sources["SZSE"] = "深交所融资融券明细当日汇总（汇总接口异常时回退）"
        except Exception as detail_error:
            errors["SZSE"] = f"summary:{summary_error.__class__.__name__};detail:{detail_error.__class__.__name__}"
    try:
        df = ak.stock_margin_detail_bse(date=stamp)
        rows = base.df_records(df)
        values = [base.finite(x.get("融资余额")) for x in rows]
        values = [x for x in values if x is not None]
        if not values:
            raise ValueError("missing financing balance")
        balances["BSE"] = sum(values)
        sources["BSE"] = "北交所融资融券明细当日汇总"
    except Exception as e:
        errors["BSE"] = e.__class__.__name__
    complete = set(balances) == {"SSE", "SZSE", "BSE"}
    return {
        "dataDate": base.iso(d), "financingBalance": sum(balances.values()) if complete else None,
        "exchangeBalances": balances, "exchangeCoverage": sorted(balances),
        "complete": complete, "errors": errors, "sources": sources,
        "scoreEligible": False,
        "scoreBlocker": "需要485个连续、同口径、按可得时间保存的完整交易日汇总" if complete else "交易所覆盖不完整",
    }


def collect_margin_v2(cutoff):
    result = _original_collect_margin(cutoff)
    day = result.get("dataDate")
    if not day:
        result["marketSummary"] = {"complete": False, "scoreEligible": False,
                                   "scoreBlocker": "没有可核验的两融交易日"}
        return result
    result["marketSummary"] = fetch_market_margin_summary(
        base.datetime.strptime(day, "%Y-%m-%d").date())
    return result


base.fetch_margin_day = fetch_margin_day_v2
base.collect_margin = collect_margin_v2

if __name__ == "__main__":
    base.main()
