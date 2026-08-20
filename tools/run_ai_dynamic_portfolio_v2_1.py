#!/usr/bin/env python3
from __future__ import annotations

import run_ai_dynamic_portfolio_v2 as dyn

_original = dyn.dynamic_build_latest


def build_latest_with_close_targets(state, ledger, prices, radar):
    # After close we must not create fills, but the latest model target should
    # still be visible to the app using the final point-in-time radar snapshot.
    if not dyn.LAST_TARGETS:
        dyn.LAST_TARGETS = dyn.target_rows(radar, state)
    return _original(state, ledger, prices, radar)


dyn.dynamic_build_latest = build_latest_with_close_targets

if __name__ == "__main__":
    raise SystemExit(dyn.main())
