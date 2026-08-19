#!/usr/bin/env python3
"""BSE-safe entrypoint for verified forward tracking.

For BSE 920xxx symbols Tencent realtime quotes are used to verify the current
session's raw open/close because Tencent fqkline currently omits those historical
rows. Older BSE entry days are not retroactively fabricated.
"""
import re
from datetime import datetime
from urllib.request import Request, urlopen

import update_strategy_backtest as legacy
from bse_market_mapping import eastmoney_secid, tencent_symbol

# Patch before importing verified wrapper so all adjusted/raw Eastmoney calls use 0.x for BSE.
legacy.secid = lambda code: eastmoney_secid(code, index_000300=True)

import update_strategy_backtest_verified as verified  # noqa: E402

_original_raw_tencent = verified.raw_tencent


def bse_today_raw(code):
    sym = tencent_symbol(code, index_000300=True)
    req = Request(
        "https://qt.gtimg.cn/q=" + sym,
        headers={
            "User-Agent": "Mozilla/5.0 AStockStrategy-BSE-Backtest/1.0",
            "Accept": "*/*",
            "Referer": "https://gu.qq.com/",
            "Cache-Control": "no-cache",
        },
    )
    with urlopen(req, timeout=12) as r:
        text = r.read().decode("gbk", "replace")
    m = re.search(r'v_[A-Za-z0-9]+="([^"]*)"', text)
    if not m:
        return {}
    f = m.group(1).split("~")
    if len(f) <= 34:
        return {}
    stamp = f[30] if len(f) > 30 else ""
    if len(stamp) < 8:
        return {}
    date = f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}"
    def n(i):
        return legacy.finite(f[i]) if len(f) > i else None
    return {date: {"open": n(5), "close": n(3), "high": n(33), "low": n(34)}}


def raw_tencent_bse(code, limit=620):
    if str(code).startswith(("8", "9")):
        try:
            return bse_today_raw(code)
        except Exception:
            return {}
    return _original_raw_tencent(code, limit)

verified.raw_tencent = raw_tencent_bse
legacy.VERSION = "v1.3-next-open-verified-bse"

if __name__ == "__main__":
    legacy.main()
