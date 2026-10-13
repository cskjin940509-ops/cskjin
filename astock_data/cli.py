# -*- coding: utf-8 -*-
"""Self-check for the astock_data foundation.

Run from the cskjin repo root:

    python -m astock_data.cli                 # full smoke test
    python -m astock_data.cli kline 600000    # fetch one kline
    python -m astock_data.cli index 000300    # index kline
    python -m astock_data.cli cross 2026-09-30
    python -m astock_data.cli calendar 2026-09
Exit code 0 = all checks pass; non-zero = a check failed.
"""
from __future__ import annotations

import sys

from .store import DataFoundation


def _ok(label: str, value) -> bool:
    print(f"  [ok] {label}: {value}")
    return True


def smoke() -> int:
    print("== astock_data self-check ==")
    df = DataFoundation()
    s = df.store

    dates = s.dates_of("jq_daily")
    _ok("jq_daily partitions", f"{len(dates)} days {dates[0]}~{dates[-1]}")

    cal = s.calendar("2026-09-01", "2026-09-30")
    _ok("calendar 2026-09", f"{len(cal)} days {cal[0]}~{cal[-1]}")

    sl = s.stock_list("2026-09-30")
    _ok("stock_list 2026-09-30", f"{len(sl)} codes, sample {sl[:3]}")

    ks = s.get_kline("600000", limit=620, end="2026-09-30")
    bad = [r for r in ks if r["date"] > "2026-09-30"]
    _ok("get_kline 600000 (point-in-time)",
        f"{len(ks)} bars, last {ks[-1]['date'] if ks else 'NA'}, "
        f"future leak rows={len(bad)}")
    if not ks:
        print("  [FAIL] kline empty for 600000")
        return 1
    if bad:
        print("  [FAIL] point-in-time leak detected")
        return 1
    sample = ks[-1]
    _ok("kline row shape", sample.keys())
    if not all(sample[f] is not None for f in ("date", "open", "close", "high", "low")):
        print("  [FAIL] kline row has null OHLC")
        return 1

    idx = s.get_index_kline("000300", limit=620, end="2026-09-30")
    _ok("index 000300", f"{len(idx)} bars, last {idx[-1]['date'] if idx else 'NA'}")
    if not idx:
        print("  [FAIL] index kline empty")
        return 1

    cons = s.index_constituents("000300", "2026-09-30")
    _ok("000300 constituents", f"{len(cons)} names, sample {cons[:3]}")

    cs = s.cross_section("jq_valuation", "2026-09-30",
                         columns=["code", "pe_ratio", "market_cap"],
                         codes=["600000", "000001"])
    _ok("valuation cross-section", f"{len(cs)} rows x {cs.shape[1]} cols")

    mg = s.margin(["600000", "000001"], "2026-09-30")
    _ok("margin cross-section", f"{len(mg)} rows")

    inds = s.industries(["600000"], "2026-09-30")
    _ok("industries", list(inds.columns) if not inds.empty else "empty")

    from . import stock_margin as sm
    det_dates = sm.available_dates()
    _ok("stock_margin detail days", det_dates)
    day = sm.load_day("2026-09-30")
    by_exch: dict[str, int] = {}
    for rec in day.values():
        by_exch[rec["exchange"]] = by_exch.get(rec["exchange"], 0) + 1
    _ok("stock_margin 2026-09-30", f"{len(day)} codes, per-exchange {by_exch}")
    if "600000" in day:
        r = day["600000"]
        _ok("stock_margin 600000 record",
            f"balance={r['balance']} netBuyExact={r['netBuyExact']}")
    audit = sm.day_audit("2026-09-30") or {}
    _ok("margin audit status", f"{audit.get('status')} matchedAStocks={audit.get('matchedAStocks')}")
    if audit.get("status") != "CROSS_SOURCE_RECONCILED":
        print("  [note] audit 仍为 PENDING，建议跑 akshare SSE 官方源交叉核对 "
              "(recon_official 子命令, 需 akshare)")
    print("\nAll checks passed.")
    return 0


def recon_official(date_str: str = "2026-09-30") -> int:
    """Cross-source reconciliation: tushare-proxy margin_detail vs akshare SSE
    official stock_margin_detail_sse. Prints matched/mismatch counts; exit 0
    if the official SSE sample agrees with the proxy on every compared stock."""
    import akshare as ak
    import pandas as pd

    from . import stock_margin as sm

    compact = date_str.replace("-", "")
    proxy_day = sm.load_day(compact)

    import time as _time

    _time.sleep(2)
    official = ak.stock_margin_detail_sse(date=compact)
    if official is None or official.empty:
        print("  [FAIL] akshare SSE official returned no rows")
        return 2
    official = official.copy()
    official["bare"] = official["标的证券代码"].astype(str).str.zfill(6)
    o_bal = dict(zip(official["bare"], official["融资余额"].astype(float)))
    o_buy = dict(zip(official["bare"], official["融资买入额"].astype(float)))
    o_repay = dict(zip(official["bare"], official["融资偿还额"].astype(float)))

    common = [c for c in proxy_day if c in o_bal]
    mism = []
    for c in common:
        p, ob = proxy_day[c], o_bal[c]
        pb = p["balance"]
        if (pd.isna(pb) and not pd.isna(ob)) or (not pd.isna(pb) and pd.isna(ob)):
            mism.append((c, "presence", pb, ob))
            continue
        if not (pd.isna(pb) or pd.isna(ob)):
            if abs(pb - ob) > 1.0:
                mism.append((c, "balance", pb, ob))
        pnet = p["netBuyExact"]
        onet = None
        if not pd.isna(o_buy.get(c)) and not pd.isna(o_repay.get(c)):
            onet = o_buy[c] - o_repay[c]
        if pnet is not None and onet is not None and abs(pnet - onet) > 1.0:
            mism.append((c, "net", pnet, onet))

    print(f"official SSE rows={len(official)} common={len(common)} mismatches={len(mism)}")
    for c, kind, a, b in mism[:10]:
        print(f"  [mismatch] {c} {kind}: proxy={a} official={b}")
    extra_official = [c for c in o_bal if c not in proxy_day]
    print(f"official-only codes (not in proxy day): {len(extra_official)}")
    return 0 if not mism else 1


def main(argv: list[str]) -> int:
    from .store import DataFoundation as DF

    arg = argv[0] if argv else "smoke"
    df = DF()
    s = df.store

    if arg == "kline":
        code = argv[1] if len(argv) > 1 else "600000"
        end = argv[2] if len(argv) > 2 else None
        rows = s.get_kline(code, 620, end=end)
        print(f"{code}: {len(rows)} bars")
        for r in rows[-5:]:
            print("  ", r)
        return 0 if rows else 2

    if arg == "index":
        idx = argv[1] if len(argv) > 1 else "000300"
        end = argv[2] if len(argv) > 2 else None
        rows = s.get_index_kline(idx, 620, end=end)
        print(f"index {idx}: {len(rows)} bars")
        for r in rows[-5:]:
            print("  ", r)
        return 0 if rows else 2

    if arg == "cross":
        date = argv[1] if len(argv) > 1 else "2026-09-30"
        cs = s.cross_section("jq_valuation", date,
                             columns=["code", "pe_ratio", "market_cap"])
        print(f"jq_valuation {date}: {cs.shape}")
        print(cs.head(10).to_string())
        return 0 if not cs.empty else 2

    if arg == "calendar":
        month = argv[1] if len(argv) > 1 else "2026-09"
        lo, hi = f"{month}-01", f"{month}-31"
        cal = s.calendar(lo, hi)
        print(f"{month}: {len(cal)} trading days")
        for d in cal:
            print("  ", d)
        return 0 if cal else 2

    if arg == "recon_official":
        target = argv[1] if len(argv) > 1 else "2026-09-30"
        return recon_official(target)

    return smoke()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
