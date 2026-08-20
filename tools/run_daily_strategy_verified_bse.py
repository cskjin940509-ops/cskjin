#!/usr/bin/env python3
"""BSE-safe production entrypoint for the verified daily scanner.

Production cohorts are generated from the same-day frozen market snapshot. Raw
OHLC validation keeps the >=2 independent-provider rule. This wrapper also fills
compatibility/diff metadata during the *same freeze operation* so future Official
cohorts never expose an empty mainlines field when selectedSectors is non-empty.
Existing Official cohorts remain immutable.

v1.9 adds exchange-published slow-money factors. B1 uses prior-published margin
financing data; B2 uses prior-published ETF share changes. Both are strictly T+1
and can never consume same-signal-day data.
"""
from datetime import datetime
import json
import re
from urllib.request import Request, urlopen

import run_daily_strategy_fast as base
import run_daily_strategy_verified as verified
import slow_money_factors as slow
from bse_market_mapping import eastmoney_secid, tencent_symbol

_original_verify_price = verified.verify_price
_original_freeze = base.freeze
_original_choose_stocks = base.choose_stocks


def secid(code):
    return eastmoney_secid(code)


def symbol(code):
    return tencent_symbol(code)


def choose_stocks_with_slow_money(selected):
    stocks, pools = _original_choose_stocks(selected)
    return slow.apply_to_stock_candidates(stocks, pools, verified.TARGET_DAY)[:2]


def tencent_same_day_snapshot(code, day):
    sym = symbol(code)
    req = Request(
        "https://qt.gtimg.cn/q=" + sym,
        headers={
            "User-Agent": "Mozilla/5.0 AStockStrategy-BSE-Verified/1.1",
            "Accept": "*/*",
            "Referer": "https://gu.qq.com/",
            "Cache-Control": "no-cache",
        },
    )
    with urlopen(req, timeout=12) as r:
        text = r.read().decode("gbk", "replace")
    m = re.search(r'v_[A-Za-z0-9]+="([^"]*)"', text)
    if not m:
        return None
    f = m.group(1).split("~")
    if len(f) <= 34:
        return None
    stamp = f[30] if len(f) > 30 else ""
    if len(stamp) < 8 or stamp[:8] != day.replace("-", ""):
        return None
    def n(i):
        return verified.finite(f[i]) if len(f) > i else None
    return {"open": n(5), "close": n(3), "high": n(33), "low": n(34), "quoteTime": stamp}


def verify_price_bse(code, day):
    if not str(code).startswith(("8", "9")):
        return _original_verify_price(code, day)
    checks = []
    try:
        tx = tencent_same_day_snapshot(code, day)
        checks.append({"provider": "腾讯实时收盘快照", "row": tx})
    except Exception as e:
        checks.append({"provider": "腾讯实时收盘快照", "row": None, "error": e.__class__.__name__})
        tx = None
    try:
        em = verified.eastmoney_raw_day(code, day)
        checks.append({"provider": "东方财富", "row": em})
    except Exception as e:
        checks.append({"provider": "东方财富", "row": None, "error": e.__class__.__name__})
        em = None
    if not tx or not em:
        return {"verified": False, "checks": checks, "reason": "fewer-than-two-bse-raw-providers"}
    mx = verified.pair_diff(tx, em)
    ok = mx is not None and mx <= 0.001
    return {
        "verified": ok,
        "rawClose": verified.finite(tx.get("close")) if ok else None,
        "maxRelDiff": mx,
        "providers": ["腾讯实时收盘快照", "东方财富"] if ok else [],
        "checks": checks,
        "rule": "北交所：腾讯同日收盘快照+东方财富未复权日线OHLC最大相对差<=0.1%",
    }


def freeze_with_compat(day, payload, selected, stocks, pools):
    """Finalize compatibility and slow-money fields atomically with signal freeze."""
    cohort = _original_freeze(day, payload, selected, stocks, pools)
    path = base.SNAPS
    arr = json.loads(path.read_text(encoding="utf-8"))
    idx = next((i for i, item in enumerate(arr) if item.get("date") == day), None)
    if idx is None:
        return cohort
    item = arr[idx]
    if item.get("status") != "Official":
        return cohort

    if not item.get("mainlines"):
        item["mainlines"] = [x.get("name") for x in (item.get("selectedSectors") or []) if x.get("name")]

    previous = next(
        (x for x in sorted(arr[:idx], key=lambda z: z.get("date", ""), reverse=True)
         if x.get("status") == "Official"),
        None,
    )
    prev_pools = (previous or {}).get("pools") or {}
    cur_pools = item.get("pools") or {}
    prev_b4 = set(prev_pools.get("B4") or [])
    cur_b4 = set(cur_pools.get("B4") or [])
    prev_any = {c for members in prev_pools.values() for c in (members or [])}
    cur_any = {c for members in cur_pools.values() for c in (members or [])}
    item["upgraded"] = sorted((cur_b4 - prev_b4) & prev_any)
    item["downgraded"] = sorted((prev_b4 - cur_b4) & cur_any)

    factors = slow.load_for_signal_date(day)
    availability = item.setdefault("factorAvailability", {})
    availability.pop("两融B1", None)
    availability.pop("ETF一级申赎B2", None)
    availability.update(slow.availability_strings(factors))
    item["slowMoneyFactor"] = {
        "state": "ready" if factors else "unavailable",
        "dataDate": factors.get("dataDate") if factors else None,
        "latency": "T+1日频",
        "B1Members": len(cur_pools.get("B1") or []),
        "B2Members": len(cur_pools.get("B2") or []),
        "principle": "只使用信号日前已经发布的交易所两融与ETF份额数据；缺失不填补。",
    }
    if factors:
        item["confidence"] = "中高" if cur_pools.get("B1") and cur_pools.get("B2") else "中"
        item["note"] = "日终扫描已冻结；B1两融与B2 ETF一级份额均按T+1已发布数据参与，B4为基础/主力/慢资金综合排序。"

    by_code = {str(s.get("code")): s for s in stocks}
    slow_keys = (
        "marginScore", "marginFactorScore", "marginData",
        "etfScore", "etfFlowScore", "etfData",
        "slowCompositeScore", "slowFactorDataDate",
    )
    for code, meta in (item.get("stocks") or {}).items():
        src = by_code.get(code) or {}
        for key in slow_keys:
            if key in src:
                meta[key] = src[key]

    available_at = item.get("availableAt") or datetime.now(base.CN).isoformat(timespec="seconds")
    for sector in item.get("selectedSectors") or []:
        sector.setdefault("availableAt", available_at)
    for meta in (item.get("stocks") or {}).values():
        meta.setdefault("availableAt", available_at)

    path.write_text(json.dumps(arr, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return item


base.sid = secid
base.choose_stocks = choose_stocks_with_slow_money
base.freeze = freeze_with_compat
verified.secid = secid
verified.symbol = symbol
verified.verify_price = verify_price_bse
verified.VERSION = "v1.9.0-verified-point-in-time-bse-slow-money"

if __name__ == "__main__":
    verified.main()
