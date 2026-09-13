#!/usr/bin/env python3
"""Robust wrapper for slow-money collection.

Uses the user-selected Tushare-compatible proxy as the primary source for
Shanghai/Shenzhen margin balances and ETF shares. Exchange endpoints remain
as a fallback/cross-check. BSE is deliberately excluded from the frozen
margin universe so current and historical observations stay comparable.
"""
from __future__ import annotations

import os
import re
import time
from io import BytesIO
from unittest.mock import patch as mock_patch

import akshare as ak
import collect_slow_money_factors as base
import requests

_original_fetch_margin_day = base.fetch_margin_day
_original_collect_margin = base.collect_margin
_original_collect_etf = base.collect_etf

PROXY_URL = os.getenv("STOCK_API_URL", "https://jiaoch.top/")


def _proxy_rows(api_name, params, fields=""):
    raw_token = os.getenv("STOCK_API_TOKEN", "").strip()
    candidates = re.findall(r"(?<![0-9a-fA-F])[0-9a-fA-F]{40,128}(?![0-9a-fA-F])", raw_token)
    token = max(candidates, key=len) if candidates else raw_token.strip("'\"")
    if not token:
        raise RuntimeError("STOCK_API_TOKEN is not configured")
    response = requests.post(
        PROXY_URL,
        json={"api_name": api_name, "token": token, "params": params,
              "fields": fields},
        headers={"Accept-Encoding": "gzip"}, timeout=45)
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"proxy api error: {payload.get('code')}")
    data = payload.get("data") or {}
    names = data.get("fields") or []
    return [dict(zip(names, values)) for values in (data.get("items") or [])]


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
    stamp = base.ds(d)
    try:
        rows = _proxy_rows("margin_detail", {"trade_date": stamp, "limit": 6000})
        merged = {}
        for r in rows:
            code = str(r.get("ts_code") or "").split(".")[0]
            suffix = str(r.get("ts_code") or "").split(".")[-1]
            if suffix not in ("SH", "SZ") or not code:
                continue
            bal = base.finite(r.get("rzye")); buy = base.finite(r.get("rzmre")); repay = base.finite(r.get("rzche"))
            merged[code] = {"code": code, "name": None, "balance": bal,
                "buyAmount": buy, "repayAmount": repay,
                "netBuyExact": (buy-repay) if buy is not None and repay is not None else None,
                "source": "用户指定Tushare兼容接口融资融券明细", "exchange": "SSE" if suffix == "SH" else "SZSE"}
        coverage = {row["exchange"] for row in merged.values()}
        if coverage == {"SSE", "SZSE"}:
            return base.iso(d), merged, {}
    except Exception:
        pass

    day, merged, errors = _original_fetch_margin_day(d)

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

    return day, merged, errors


def _first_finite(records, names):
    for row in records:
        for name in names:
            value = base.finite(row.get(name))
            if value is not None:
                return value
    return None


def _sum_financing_balance_frame(df):
    """Sum an official detail table without assuming a fixed column count."""
    if df is None or df.empty:
        return None
    column = next((c for c in df.columns if str(c).strip() in ("融资余额", "融资余额(元)")), None)
    if column is None:
        return None
    values = [base.finite(v.replace(",", "") if isinstance(v, str) else v)
              for v in df[column].tolist()]
    values = [v for v in values if v is not None]
    return sum(values) if values else None


def _fetch_szse_detail_total_raw(stamp):
    """Read SZSE's official xlsx while preserving its published headers.

    AKShare currently replaces the complete column list with eight fixed names;
    an added exchange column therefore raises ValueError before data is returned.
    """
    response = requests.get(
        "https://www.szse.cn/api/report/ShowReport",
        params={"SHOWTYPE": "xlsx", "CATALOGID": "1837_xxpl",
                "txtDate": f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}",
                "tab2PAGENO": "1", "TABKEY": "tab2"},
        headers={"Referer": "https://www.szse.cn/disclosure/margin/margin/index.html",
                 "User-Agent": "Mozilla/5.0"}, timeout=30)
    response.raise_for_status()
    return _sum_financing_balance_frame(base.pd.read_excel(BytesIO(response.content), engine="openpyxl"))


def fetch_market_margin_summary(d):
    """Fetch exchange totals without pretending a partial sum is complete.

    SSE publishes a historical summary table; SZSE exposes a one-day summary.
    AKShare currently has no consistently documented BSE summary call, so the
    BSE balance is summed from that day's official detail when available.
    """
    stamp = base.ds(d)
    try:
        rows = _proxy_rows("margin", {"trade_date": stamp, "limit": 10})
        balances = {str(r.get("exchange_id")): base.finite(r.get("rzye")) for r in rows
                    if str(r.get("exchange_id")) in ("SSE", "SZSE")}
        balances = {k: v for k, v in balances.items() if v is not None}
        complete = set(balances) == {"SSE", "SZSE"}
        return {"dataDate": base.iso(d),
            "financingBalance": sum(balances.values()) if complete else None,
            "exchangeBalances": balances, "exchangeCoverage": sorted(balances),
            "exchangeUniverse": ["SSE", "SZSE"], "excludedExchanges": ["BSE"],
            "complete": complete,
            "errors": {} if complete else {"coverage": "missing SSE or SZSE"},
            "sources": {k: "用户指定Tushare兼容接口" for k in balances},
            "scoreEligible": complete,
            "scoreBlocker": None if complete else "沪深交易所覆盖不完整"}
    except Exception as proxy_error:
        proxy_error_name = proxy_error.__class__.__name__

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
            try:
                value = _fetch_szse_detail_total_raw(stamp)
                if value is None:
                    raise ValueError("missing financing balance")
                balances["SZSE"] = value
                sources["SZSE"] = "深交所官方明细xlsx当日汇总（绕过固定列数封装）"
            except Exception as raw_error:
                errors["SZSE"] = (f"summary:{summary_error.__class__.__name__};"
                                  f"detail:{detail_error.__class__.__name__};"
                                  f"raw:{raw_error.__class__.__name__}")
    errors["primaryProxy"] = proxy_error_name
    complete = set(balances) == {"SSE", "SZSE"}
    return {
        "dataDate": base.iso(d), "financingBalance": sum(balances.values()) if complete else None,
        "exchangeBalances": balances, "exchangeCoverage": sorted(balances),
        "exchangeUniverse": ["SSE", "SZSE"], "excludedExchanges": ["BSE"],
        "complete": complete, "errors": errors, "sources": sources,
        "scoreEligible": complete,
        "scoreBlocker": None if complete else "沪深交易所覆盖不完整",
    }


def _proxy_etf_snapshot(d):
    stamp = base.ds(d)
    rows = _proxy_rows("fund_share", {"trade_date": stamp, "limit": 6000})
    snapshot = {}
    for r in rows:
        ts_code = str(r.get("ts_code") or "")
        code, _, suffix = ts_code.partition(".")
        shares = base.finite(r.get("fd_share"))
        if not code or suffix not in ("SH", "SZ") or shares is None:
            continue
        snapshot[code] = {"code": code, "name": None, "shares": shares,
                          "exchange": "SSE" if suffix == "SH" else "SZSE"}
    return base.iso(d), snapshot


def collect_etf_v2(cutoff):
    snapshots = []
    errors = []
    for i in range(45):
        d = cutoff - base.timedelta(days=i)
        if d.weekday() >= 5:
            continue
        try:
            day, rows = _proxy_etf_snapshot(d)
            if rows:
                snapshots.append((day, rows))
                if len(snapshots) >= 21:
                    break
        except Exception as e:
            errors.append(f"{base.iso(d)}:{e.__class__.__name__}")
    if not snapshots:
        fallback = _original_collect_etf(cutoff)
        fallback.setdefault("errors", {})["primaryProxy"] = errors[:5] or ["not-configured"]
        return fallback

    # Reuse the stable aggregation implementation by supplying proxy snapshots
    # through its exchange collectors; spot prices remain an estimate only.
    sse = [(d, {k:v for k,v in rows.items() if v["exchange"] == "SSE"}, None) for d,rows in snapshots]
    szse = [(d, {k:v for k,v in rows.items() if v["exchange"] == "SZSE"}, None) for d,rows in snapshots]
    with mock_patch.object(base, "collect_sse_etf", return_value=sse), \
         mock_patch.object(base, "collect_szse_etf", return_value=(szse, None)):
        result = _original_collect_etf(cutoff)
    result["source"] = ["用户指定Tushare兼容接口ETF份额", "东方财富ETF行情仅用于金额估算"]
    result["primarySource"] = "https://jiaoch.top/"
    if errors:
        result.setdefault("errors", {})["skippedDates"] = errors[:5]
    return result


def collect_margin_v2(cutoff):
    result = _original_collect_margin(cutoff)
    day = result.get("dataDate")
    if not day:
        result["marketSummary"] = {"complete": False, "scoreEligible": False,
                                   "scoreBlocker": "没有可核验的两融交易日"}
        return result
    start = base.datetime.strptime(day, "%Y-%m-%d").date()
    checks = []
    for i in range(10):
        candidate = start - base.timedelta(days=i)
        if candidate.weekday() >= 5:
            continue
        summary = fetch_market_margin_summary(candidate)
        checks.append({"dataDate": summary.get("dataDate"),
                       "complete": summary.get("complete")})
        if summary.get("complete"):
            summary["latestDateChecks"] = checks
            result["marketSummary"] = summary
            break
    else:
        result["marketSummary"] = summary
        result["marketSummary"]["latestDateChecks"] = checks
    return result


base.fetch_margin_day = fetch_margin_day_v2
base.collect_margin = collect_margin_v2
base.collect_etf = collect_etf_v2

if __name__ == "__main__":
    base.main()
