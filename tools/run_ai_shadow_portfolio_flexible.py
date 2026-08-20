#!/usr/bin/env python3
"""Production wrapper for the smart shadow portfolio with flexible portfolio breadth.

This keeps the original point-in-time decision engine and immutable ledger, while
removing the arbitrary total position-count cap and allowing gross exposure up to
100%. Single-stock, sector, liquidity, chase-risk, T+1, exit, and daily turnover
controls remain unchanged.
"""
from __future__ import annotations

import run_ai_shadow_portfolio as base

# v1.1 changes only portfolio breadth / gross exposure constraints.
base.STRATEGY_VERSION = "v1.1-ai-shadow-flexible-breadth-full-exposure"
base.MAX_POSITIONS = 1_000_000_000  # Effectively uncapped; no portfolio-count gate.
base.MAX_GROSS_WEIGHT = 1.00

_original_build_latest = base.build_latest


def build_latest_with_flexible_limits(state, ledger, prices, radar):
    out = _original_build_latest(state, ledger, prices, radar)
    out["strategyVersion"] = base.STRATEGY_VERSION
    rules = out.setdefault("rulesZh", {})
    rules["position"] = (
        "持仓股票数不设上限，总仓位允许达到100%；单股最高15%、单板块最高25%。"
        "是否满仓由合格候选数量和评分决定，没有合格机会仍允许保留现金。"
    )
    return out


base.build_latest = build_latest_with_flexible_limits


if __name__ == "__main__":
    raise SystemExit(base.main())
