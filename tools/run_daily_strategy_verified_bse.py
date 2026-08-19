#!/usr/bin/env python3
"""BSE-safe production entrypoint for the verified daily scanner."""
import run_daily_strategy_fast as base
import run_daily_strategy_verified as verified
from bse_market_mapping import eastmoney_secid, tencent_symbol


def secid(code):
    return eastmoney_secid(code)


def symbol(code):
    return tencent_symbol(code)

# base.choose_stocks -> shist -> base.sid; verified price audit -> verified.secid/symbol.
base.sid = secid
verified.secid = secid
verified.symbol = symbol
verified.VERSION = "v1.7.1-verified-point-in-time-bse"

if __name__ == "__main__":
    verified.main()
