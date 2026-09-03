#!/usr/bin/env python3
"""Production entry point for the 20M fund-NAV/capacity-aware shadow portfolio."""
from __future__ import annotations

# Importing v2.1 installs the post-close target-display wrapper.
import run_ai_dynamic_portfolio_v2_1  # noqa: F401
import run_ai_dynamic_portfolio_v2 as dyn


dyn.STRATEGY_VERSION = "v3.0-fund-nav-capacity-point-in-time"


if __name__ == "__main__":
    raise SystemExit(dyn.main())
