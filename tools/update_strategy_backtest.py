#!/usr/bin/env python3
"""Incrementally track frozen Daily Cohorts without rewriting their membership.

Entry convention: the first tradable session after the cohort date, at that
session's open. Returns are measured at the 1/5/10/20/60-session close. This
keeps the report free of close-to-close look-ahead bias.
"""

from __future__ import annotations

import json
import math
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


CN = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / "astock_snapshots" / "index.json"
HORIZONS = {"1D": 1, "5D": 5, "10D": 10, "20D": 20, "60D": 60}
MAX_TRACKING_DAYS = 540
VERSION = "v1.0-next-open-tracker"


def finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def secid(code: str) -> str:
    return ("1." if code == "000300" or code.startswith(("5", "6", "9")) else "0.") + code


def fetch_kline_eastmoney(code: str, limit: int = 620) -> list[dict]:
    query = {
        "secid": secid(code),
        "klt": 101,
        "fqt": 1,
        "lmt": limit,
        "end": "20500101",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
    }
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?" + urlencode(query)
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 AStockStrategy-Backtest/1.0",
            "Accept": "application/json",
            "Referer": "https://quote.eastmoney.com/",
        },
    )
    with urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8", "replace"))
    rows = []
    for raw in ((payload.get("data") or {}).get("klines") or []):
        fields = raw.split(",")
        if len(fields) < 7:
            continue
        opened, closed = finite(fields[1]), finite(fields[2])
        high, low = finite(fields[3]), finite(fields[4])
        if not fields[0] or opened is None or closed is None:
            continue
        rows.append(
            {
                "date": fields[0],
                "open": opened,
                "close": closed,
                "high": high if high is not None else max(opened, closed),
                "low": low if low is not None else min(opened, closed),
                "amount": finite(fields[6]),
            }
        )
    rows.sort(key=lambda item: item["date"])
    return rows


def fetch_kline_tencent(code: str, limit: int = 620) -> list[dict]:
    prefix = (
        "bj"
        if code.startswith(("8", "9"))
        else ("sh" if code == "000300" or code.startswith(("5", "6")) else "sz")
    )
    symbol = prefix + code
    url = (
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
        + urlencode({"param": f"{symbol},day,,,{limit},qfq"})
    )
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 AStockStrategy-Backtest/1.0",
            "Accept": "application/json",
            "Referer": "https://gu.qq.com/",
        },
    )
    with urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8", "replace"))
    root = (payload.get("data") or {}).get(symbol) or {}
    raw_rows = root.get("qfqday") or root.get("day") or []
    rows = []
    for fields in raw_rows:
        if not isinstance(fields, list) or len(fields) < 5:
            continue
        opened, closed = finite(fields[1]), finite(fields[2])
        high, low = finite(fields[3]), finite(fields[4])
        if not fields[0] or opened is None or closed is None:
            continue
        rows.append(
            {
                "date": fields[0],
                "open": opened,
                "close": closed,
                "high": high if high is not None else max(opened, closed),
                "low": low if low is not None else min(opened, closed),
                "amount": None,
            }
        )
    rows.sort(key=lambda item: item["date"])
    return rows


def fetch_kline(code: str, limit: int = 620) -> list[dict]:
    errors = []
    for provider in (fetch_kline_tencent, fetch_kline_eastmoney):
        try:
            rows = provider(code, limit)
            if rows:
                return rows
            errors.append(provider.__name__ + ":empty")
        except Exception as error:
            errors.append(provider.__name__ + ":" + error.__class__.__name__)
    raise RuntimeError(";".join(errors))


def rounded(value):
    return round(value, 6) if value is not None and math.isfinite(value) else None


def return_at(rows: list[dict], entry_price: float, index: int):
    if len(rows) <= index or not entry_price:
        return None
    close = finite(rows[index].get("close"))
    return (close / entry_price - 1.0) if close is not None else None


def benchmark_return(benchmark: list[dict], entry_date: str, as_of: str):
    eligible = [bar for bar in benchmark if entry_date <= bar["date"] <= as_of]
    if not eligible:
        return None
    entry = finite(eligible[0].get("open"))
    close = finite(eligible[-1].get("close"))
    if not entry or close is None:
        return None
    return close / entry - 1.0


def performance_for(rows: list[dict], cohort_date: str, benchmark: list[dict]) -> dict | None:
    future = [bar for bar in rows if bar["date"] > cohort_date]
    if not future:
        return None
    entry = future[0]
    entry_price = finite(entry.get("open")) or finite(entry.get("close"))
    if not entry_price:
        return None

    result = {
        "entryRule": "次一交易日开盘等权",
        "entryDate": entry["date"],
        "entryPrice": rounded(entry_price),
        "asOf": future[-1]["date"],
        "tradingDays": len(future),
        "source": "腾讯/东方财富前复权日线",
    }
    for label, sessions in HORIZONS.items():
        if len(future) < sessions:
            continue
        bar = future[sessions - 1]
        value = return_at(future, entry_price, sessions - 1)
        bench = benchmark_return(benchmark, entry["date"], bar["date"])
        result[label] = {
            "return": rounded(value),
            "benchmark": rounded(bench),
            "alpha": rounded(value - bench) if value is not None and bench is not None else None,
            "asOf": bar["date"],
            "mature": True,
        }

    current = return_at(future, entry_price, len(future) - 1)
    current_benchmark = benchmark_return(benchmark, entry["date"], future[-1]["date"])
    result["current"] = {
        "return": rounded(current),
        "benchmark": rounded(current_benchmark),
        "alpha": rounded(current - current_benchmark)
        if current is not None and current_benchmark is not None
        else None,
        "asOf": future[-1]["date"],
    }
    highs = [finite(bar.get("high")) for bar in future]
    lows = [finite(bar.get("low")) for bar in future]
    highs = [value for value in highs if value is not None]
    lows = [value for value in lows if value is not None]
    result["MFE"] = {
        "return": rounded(max(highs) / entry_price - 1.0) if highs else None,
        "asOf": future[-1]["date"],
    }
    result["MAE"] = {
        "return": rounded(min(lows) / entry_price - 1.0) if lows else None,
        "asOf": future[-1]["date"],
    }
    return result


def metric(performance: dict, label: str, field: str = "return"):
    value = performance.get(label)
    if isinstance(value, dict):
        return finite(value.get(field))
    return finite(value)


def aggregate(codes: list[str], stock_performance: dict[str, dict]) -> dict:
    output = {}
    for label in [*HORIZONS, "current", "MFE", "MAE"]:
        values = [metric(stock_performance.get(code) or {}, label) for code in codes]
        values = [value for value in values if value is not None]
        if not values:
            continue
        alphas = [metric(stock_performance.get(code) or {}, label, "alpha") for code in codes]
        alphas = [value for value in alphas if value is not None]
        dates = [
            (stock_performance.get(code) or {}).get(label, {}).get("asOf")
            for code in codes
            if isinstance((stock_performance.get(code) or {}).get(label), dict)
        ]
        output[label] = {
            "return": rounded(statistics.fmean(values)),
            "median": rounded(statistics.median(values)),
            "alpha": rounded(statistics.fmean(alphas)) if alphas else None,
            "hitRate": rounded(sum(value > 0 for value in values) / len(values)),
            "members": len(values),
            "asOf": max((date for date in dates if date), default=None),
        }
    return output


def snapshot_is_trackable(snapshot: dict, now: datetime) -> bool:
    has_members = bool(snapshot.get("stocks")) or any(
        snapshot.get("pools", {}).get(pool) for pool in ("B0", "B1", "B2", "B3", "B4")
    )
    if snapshot.get("status") != "Official" or not has_members:
        return False
    try:
        selected = datetime.strptime(snapshot["date"], "%Y-%m-%d").replace(tzinfo=CN)
    except (KeyError, TypeError, ValueError):
        return False
    return timedelta(days=-2) <= now - selected <= timedelta(days=MAX_TRACKING_DAYS)


def update_all(root: Path | None = None, now: datetime | None = None) -> dict:
    root = root or ROOT
    snapshot_path = root / "astock_snapshots" / "index.json"
    if not snapshot_path.exists():
        return {"state": "skipped", "reason": "snapshot index missing"}

    snapshots = json.loads(snapshot_path.read_text(encoding="utf-8"))
    now = now or datetime.now(CN)
    tracked = [item for item in snapshots if snapshot_is_trackable(item, now)]
    codes = sorted(
        {
            code
            for item in tracked
            for code in set((item.get("stocks") or {}).keys())
            | {code for pool in (item.get("pools") or {}).values() for code in pool}
        }
    )
    if not tracked or not codes:
        return {"state": "skipped", "reason": "no trackable cohorts"}

    history = {}
    failures = {}
    requested = ["000300", *codes]
    with ThreadPoolExecutor(max_workers=14) as executor:
        futures = {executor.submit(fetch_kline, code): code for code in requested}
        for future in as_completed(futures):
            code = futures[future]
            try:
                rows = future.result()
                if rows:
                    history[code] = rows
                else:
                    failures[code] = "empty"
            except Exception as error:  # Provider errors must not rewrite frozen cohorts.
                failures[code] = error.__class__.__name__

    benchmark = history.get("000300") or []
    updated = 0
    stamp = now.isoformat(timespec="seconds")
    for item in tracked:
        stock_performance = dict(item.get("stockPerformance") or {})
        for code in sorted(
            set((item.get("stocks") or {}).keys())
            | {code for pool in (item.get("pools") or {}).values() for code in pool}
        ):
            calculated = performance_for(history.get(code) or [], item["date"], benchmark)
            if calculated is not None:
                stock_performance[code] = calculated
        if not stock_performance:
            continue

        pool_performance = {
            pool: aggregate(list(codes_in_pool or []), stock_performance)
            for pool, codes_in_pool in (item.get("pools") or {}).items()
        }
        sectors = {}
        for code, meta in (item.get("stocks") or {}).items():
            name = (meta or {}).get("sector") or "未分类"
            sectors.setdefault(name, []).append(code)
        sector_performance = {
            sector: aggregate(sector_codes, stock_performance)
            for sector, sector_codes in sectors.items()
        }
        item["stockPerformance"] = stock_performance
        item["poolPerformance"] = pool_performance
        item["sectorPerformance"] = sector_performance
        item["trackingUpdatedAt"] = stamp
        item["backtestMethod"] = {
            "entry": "信号日后一交易日开盘",
            "exit": "第1/5/10/20/60个交易日收盘",
            "weight": "池内等权",
            "benchmark": "沪深300",
            "price": "腾讯优先、东方财富兜底的前复权日线",
            "version": VERSION,
        }
        updated += 1

    if updated:
        snapshot_path.write_text(
            json.dumps(snapshots, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return {
        "state": "updated" if updated else "unchanged",
        "cohorts": updated,
        "symbols": len(codes),
        "histories": len(history) - (1 if "000300" in history else 0),
        "failures": failures,
        "trackingUpdatedAt": stamp if updated else None,
        "method": VERSION,
    }


def main():
    print(json.dumps(update_all(), ensure_ascii=False))


if __name__ == "__main__":
    main()

