#!/usr/bin/env python3
"""Robust wrapper for slow-money collection.

Adds SZSE retry/backoff and BSE margin detail without changing the v1 factor
semantics. ETF collection remains exchange-share based.
"""
from __future__ import annotations

import time
import akshare as ak
import collect_slow_money_factors as base

_original_fetch_margin_day = base.fetch_margin_day


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


base.fetch_margin_day = fetch_margin_day_v2

if __name__ == "__main__":
    base.main()
