#!/usr/bin/env python3
"""逐日跟踪所有已冻结 Official 股票与固定成员组合净值。

原则：
- 只在已有可审计入场价的 stockPerformance 上扩展逐日路径；
- Official 入场仍沿用“信号日后一交易日可成交开盘”；
- 个股退出当前池后历史记录继续保留；
- 固定成员组合中停牌/缺少当日 bar 的成员使用上一净值，不从分母删除；
- 平均个股累计收益是诊断指标，strategyNavReturn 才是固定成员组合收益。
"""
from __future__ import annotations

import json
import math
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

# Importing display_ready installs the current three-source / BSE-aware verified
# history functions onto update_strategy_backtest without executing its main().
import update_strategy_tracking_display_ready as display_ready  # noqa: F401
import update_strategy_backtest as legacy

CN = legacy.CN
ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / "astock_snapshots" / "index.json"
TRACK_DIR = ROOT / "astock_tracking"
TRACK_LATEST = TRACK_DIR / "latest.json"
VERSION = "v2.6-daily-path-fixed-member-nav"
MAX_DAYS = 540


def finite(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def rounded(v):
    return round(v, 8) if v is not None and math.isfinite(v) else None


def cohort_codes(item):
    codes = set((item.get("stocks") or {}).keys())
    for values in (item.get("pools") or {}).values():
        codes.update(str(c) for c in (values or []) if c)
    return sorted(codes)


def official_trackable(item, now):
    if item.get("status") != "Official" or not cohort_codes(item):
        return False
    try:
        selected = datetime.strptime(item["date"], "%Y-%m-%d").replace(tzinfo=CN)
    except Exception:
        return False
    return timedelta(days=-2) <= now - selected <= timedelta(days=MAX_DAYS)


def bar_map(rows):
    return {str(x.get("date")): x for x in rows if x.get("date")}


def entry_adjusted(perf, rows):
    p = finite(perf.get("returnEntryPriceAdjusted"))
    if p:
        return p
    entry_date = perf.get("entryDate")
    row = next((x for x in rows if x.get("date") == entry_date), None)
    return finite((row or {}).get("open")) or finite((row or {}).get("close"))


def daily_stock_path(rows, perf, benchmark):
    entry_date = perf.get("entryDate")
    if not entry_date:
        return None
    entry = entry_adjusted(perf, rows)
    if not entry:
        return None
    future = [x for x in rows if str(x.get("date") or "") >= entry_date]
    if not future:
        return None

    bench_future = [x for x in benchmark if str(x.get("date") or "") >= entry_date]
    bench_entry = None
    if bench_future:
        bench_entry = finite(bench_future[0].get("open")) or finite(bench_future[0].get("close"))
    bmap = bar_map(bench_future)

    series = []
    prev_close = entry
    prev_bench_close = bench_entry
    last_bench_close = bench_entry
    peak_nav = 1.0
    max_dd = 0.0
    max_high = None
    min_low = None

    for bar in future:
        day = str(bar.get("date"))
        close = finite(bar.get("close"))
        high = finite(bar.get("high"))
        low = finite(bar.get("low"))
        if close is None:
            continue
        daily_ret = close / prev_close - 1.0 if prev_close else None
        cum_ret = close / entry - 1.0
        prev_close = close
        if high is not None:
            max_high = high if max_high is None else max(max_high, high)
        if low is not None:
            min_low = low if min_low is None else min(min_low, low)

        brow = bmap.get(day)
        if brow is not None and finite(brow.get("close")) is not None:
            last_bench_close = finite(brow.get("close"))
        bench_daily = None
        bench_cum = None
        if last_bench_close is not None and bench_entry:
            bench_cum = last_bench_close / bench_entry - 1.0
            if prev_bench_close:
                bench_daily = last_bench_close / prev_bench_close - 1.0
            prev_bench_close = last_bench_close

        nav = 1.0 + cum_ret
        peak_nav = max(peak_nav, nav)
        dd = nav / peak_nav - 1.0 if peak_nav else 0.0
        max_dd = min(max_dd, dd)
        series.append({
            "date": day,
            "close": rounded(close),
            "dailyReturn": rounded(daily_ret),
            "cumulativeReturn": rounded(cum_ret),
            "benchmarkDailyReturn": rounded(bench_daily),
            "benchmarkCumulativeReturn": rounded(bench_cum),
            "cumulativeAlpha": rounded(cum_ret - bench_cum) if bench_cum is not None else None,
            "drawdown": rounded(dd),
        })

    if not series:
        return None
    last = series[-1]
    return {
        "dailySeries": series,
        "dailyReturn": last.get("dailyReturn"),
        "cumulativeReturn": last.get("cumulativeReturn"),
        "cumulativeAlpha": last.get("cumulativeAlpha"),
        "maxDrawdown": rounded(max_dd),
        "dailyPathMFE": rounded(max_high / entry - 1.0) if max_high is not None else None,
        "dailyPathMAE": rounded(min_low / entry - 1.0) if min_low is not None else None,
        "dailyPathAsOf": last.get("date"),
        "dailyPathVersion": VERSION,
    }


def component_map(perf):
    out = {}
    for x in perf.get("dailySeries") or []:
        day = x.get("date")
        cum = finite(x.get("cumulativeReturn"))
        if day and cum is not None:
            out[str(day)] = 1.0 + cum
    return out


def pool_nav(item, members, stock_perf, benchmark):
    members = list(dict.fromkeys(str(c) for c in members if c))
    if not members:
        return None
    cohort_date = item.get("date")
    calendar = [x for x in benchmark if str(x.get("date") or "") > str(cohort_date or "")]
    if not calendar:
        return None

    maps = {code: component_map(stock_perf.get(code) or {}) for code in members}
    entered = [code for code in members if maps.get(code)]
    if not entered:
        return None

    first_bench = calendar[0]
    bench_entry = finite(first_bench.get("open")) or finite(first_bench.get("close"))
    last_component = {code: 1.0 for code in members}
    prev_pool = 1.0
    peak_pool = 1.0
    max_dd = 0.0
    series = []

    for bar in calendar:
        day = str(bar.get("date"))
        # Missing/suspended members stay at their previous component NAV. Members
        # whose verified entry is not available yet remain cash at 1.0.
        for code in members:
            value = (maps.get(code) or {}).get(day)
            if value is not None:
                last_component[code] = value
        nav = statistics.fmean(last_component.values())
        daily_ret = nav / prev_pool - 1.0 if prev_pool else None
        prev_pool = nav
        peak_pool = max(peak_pool, nav)
        dd = nav / peak_pool - 1.0 if peak_pool else 0.0
        max_dd = min(max_dd, dd)
        bench_close = finite(bar.get("close"))
        bench_cum = bench_close / bench_entry - 1.0 if bench_close is not None and bench_entry else None
        series.append({
            "date": day,
            "nav": rounded(nav),
            "dailyReturn": rounded(daily_ret),
            "cumulativeReturn": rounded(nav - 1.0),
            "benchmarkCumulativeReturn": rounded(bench_cum),
            "alpha": rounded((nav - 1.0) - bench_cum) if bench_cum is not None else None,
            "drawdown": rounded(dd),
        })

    if not series:
        return None
    current_returns = {code: last_component[code] - 1.0 for code in entered}
    values = list(current_returns.values())
    n_all = len(members)
    contributions = sorted(
        ({"code": code, "return": rounded(ret), "contribution": rounded(ret / n_all)} for code, ret in current_returns.items()),
        key=lambda x: x["contribution"],
        reverse=True,
    )
    last = series[-1]
    return {
        "strategyNav": last.get("nav"),
        "strategyNavReturn": last.get("cumulativeReturn"),
        "dailyReturn": last.get("dailyReturn"),
        "benchmarkCumulativeReturn": last.get("benchmarkCumulativeReturn"),
        "navAlpha": last.get("alpha"),
        "averageCumReturn": rounded(statistics.fmean(values)),
        "medianCumReturn": rounded(statistics.median(values)),
        "winRateCurrent": rounded(sum(v > 0 for v in values) / len(values)),
        "maxDrawdown": rounded(max_dd),
        "coverage": rounded(len(entered) / n_all),
        "membersFixed": n_all,
        "membersWithVerifiedEntry": len(entered),
        "dailySeries": series,
        "topContributors": contributions[:3],
        "bottomContributors": list(reversed(contributions[-3:])),
        "navAsOf": last.get("date"),
        "navRuleZh": "信号日后一交易日起固定成员等权；未形成可审计入场的成员保留现金；停牌/缺bar成员沿用上一净值，不从分母删除。",
        "navVersion": VERSION,
    }


def main():
    if not SNAPSHOTS.exists():
        print(json.dumps({"state": "skip", "reason": "snapshot index missing"}, ensure_ascii=False))
        return
    snapshots = json.loads(SNAPSHOTS.read_text(encoding="utf-8"))
    now = datetime.now(CN)
    tracked = [x for x in snapshots if official_trackable(x, now)]
    if not tracked:
        print(json.dumps({"state": "skip", "reason": "no trackable official cohorts"}, ensure_ascii=False))
        return

    codes = sorted({c for item in tracked for c in cohort_codes(item)})
    requested = ["000300", *codes]
    histories = {}
    failures = {}
    with ThreadPoolExecutor(max_workers=12) as ex:
        futures = {ex.submit(legacy.fetch_kline, code): code for code in requested}
        for future in as_completed(futures):
            code = futures[future]
            try:
                rows = future.result()
                if rows:
                    histories[code] = rows
                else:
                    failures[code] = "empty"
            except Exception as e:
                failures[code] = e.__class__.__name__

    benchmark = histories.get("000300") or []
    if not benchmark:
        print(json.dumps({"state": "skip", "reason": "benchmark unavailable", "failures": failures}, ensure_ascii=False))
        return

    updated = 0
    cohort_summary = []
    stamp = now.isoformat(timespec="seconds")
    for item in tracked:
        stock_perf = dict(item.get("stockPerformance") or {})
        changed_stocks = 0
        for code in cohort_codes(item):
            perf = dict(stock_perf.get(code) or {})
            # Do not invent an entry: the verified tracker must have established it.
            if not perf.get("entryDate") or finite(perf.get("entryPrice")) is None:
                continue
            path = daily_stock_path(histories.get(code) or [], perf, benchmark)
            if path:
                perf.update(path)
                stock_perf[code] = perf
                changed_stocks += 1
        if not changed_stocks:
            continue

        pool_perf = dict(item.get("poolPerformance") or {})
        for pool, members in (item.get("pools") or {}).items():
            nav = pool_nav(item, members or [], stock_perf, benchmark)
            if nav:
                existing = dict(pool_perf.get(pool) or {})
                existing.update(nav)
                pool_perf[pool] = existing

        item["stockPerformance"] = stock_perf
        item["poolPerformance"] = pool_perf
        item["dailyTrackingUpdatedAt"] = stamp
        item["dailyTrackingMethod"] = {
            "individual": "可审计入场价起逐交易日收益、累计收益、MFE/MAE与最大回撤",
            "portfolio": "冻结批次固定成员等权净值；停牌成员净值延续，缺失成员不删除",
            "version": VERSION,
        }
        updated += 1
        cohort_summary.append({
            "date": item.get("date"),
            "trackingUse": item.get("trackingUse"),
            "stocksUpdated": changed_stocks,
            "pools": {k: {"累计组合收益": v.get("strategyNavReturn"), "今日组合收益": v.get("dailyReturn")} for k, v in pool_perf.items() if isinstance(v, dict) and v.get("strategyNavReturn") is not None},
        })

    if updated:
        SNAPSHOTS.write_text(json.dumps(snapshots, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    TRACK_DIR.mkdir(parents=True, exist_ok=True)
    summary = {
        "schemaVersion": 1,
        "updatedAt": stamp,
        "method": VERSION,
        "cohortsUpdated": updated,
        "symbolsRequested": len(codes),
        "symbolsWithHistory": max(0, len(histories) - 1),
        "failures": failures,
        "cohorts": cohort_summary,
        "noteZh": "个股逐日收益与固定成员组合净值持续保留历史失败/退出成员，避免幸存者偏差。",
    }
    TRACK_LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"state": "updated" if updated else "unchanged", **summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
