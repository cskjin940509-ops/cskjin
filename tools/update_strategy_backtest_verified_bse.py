#!/usr/bin/env python3
"""BSE-safe entrypoint for verified forward tracking."""
import update_strategy_backtest as legacy
from bse_market_mapping import eastmoney_secid

# Patch before importing verified wrapper so all historical and raw Eastmoney calls use 0.x for BSE.
legacy.secid = lambda code: eastmoney_secid(code, index_000300=True)

import update_strategy_backtest_verified as verified  # noqa: E402,F401

legacy.VERSION = "v1.2-next-open-verified-bse"

if __name__ == "__main__":
    legacy.main()
