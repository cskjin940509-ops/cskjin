#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_ai_shadow_portfolio as base  # noqa: E402
import run_ai_dynamic_portfolio_v2 as dynamic  # noqa: E402


class ShadowPortfolioTests(unittest.TestCase):
    def test_capital_migration_preserves_fills_and_adds_cash(self):
        state = {
            "initialCapital": 1_000_000.0,
            "cash": 300_000.0,
            "positions": {"000001": {"code": "000001", "qty": 10_000}},
            "navHistory": [{"date": "2026-08-20", "nav": 1_010_000.0}],
            "benchmarkTracking": {"startedAt": "2026-08-20T10:00:00+08:00"},
            "capitalEvents": [],
        }
        when = datetime.fromisoformat("2026-09-03T16:00:00+08:00")
        event = base.migrate_capital_capacity(state, when)
        self.assertIsNotNone(event)
        self.assertEqual(state["initialCapital"], 20_000_000.0)
        self.assertEqual(state["cash"], 19_300_000.0)
        self.assertEqual(state["positions"]["000001"]["qty"], 10_000)
        self.assertEqual(len(state["legacyNavHistory"]), 1)
        self.assertFalse(event["retroactive"])
        self.assertIsNone(base.migrate_capital_capacity(state, when))
        self.assertEqual(len(state["capitalEvents"]), 1)

    def test_rebalance_is_idempotent_and_enforces_t_plus_one(self):
        state = {
            "initialCapital": 20_000_000.0,
            "cash": 20_000_000.0,
            "realizedPnl": 0.0,
            "positions": {},
            "dailyControl": {},
        }
        ledger: list[dict] = []
        prices = {"000001": 10.0}
        target = {
            "code": "000001",
            "name": "测试股票",
            "sector": "测试板块",
            "score": 80.0,
            "referencePrice": 10.0,
            "priceSource": "测试行情",
            "reasonZh": "测试目标",
            "targetWeight": 0.15,
            "targetWeightPct": 15.0,
        }
        day_one = datetime.fromisoformat("2026-09-03T10:00:00+08:00")
        day_two = datetime.fromisoformat("2026-09-04T10:00:00+08:00")
        with patch.object(base, "now_cn", return_value=day_one), patch.object(
            dynamic, "target_rows", return_value=[target]
        ):
            first = dynamic.dynamic_entries(state, ledger, {}, prices)
            second = dynamic.dynamic_entries(state, ledger, {}, prices)
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 0)
        self.assertEqual(len(ledger), 1)

        with patch.object(base, "now_cn", return_value=day_one), patch.object(
            dynamic, "target_rows", return_value=[]
        ):
            same_day_exit = dynamic.dynamic_entries(state, ledger, {}, prices)
        self.assertEqual(same_day_exit, [])
        self.assertIn("000001", state["positions"])

        with patch.object(base, "now_cn", return_value=day_two), patch.object(
            dynamic, "target_rows", return_value=[]
        ):
            next_day_exit = dynamic.dynamic_entries(state, ledger, {}, prices)
        self.assertEqual(len(next_day_exit), 1)
        self.assertEqual(next_day_exit[0]["side"], "SELL")
        self.assertNotIn("000001", state["positions"])

    def test_stale_radar_is_rejected(self):
        now = datetime.fromisoformat("2026-09-03T10:30:01+08:00")
        fresh, age = base.radar_freshness({"capturedAt": "2026-09-03T10:15:00+08:00"}, now)
        self.assertFalse(fresh)
        self.assertEqual(age, 901.0)
        fresh, age = base.radar_freshness({"capturedAt": "2026-09-03T10:20:00+08:00"}, now)
        self.assertTrue(fresh)
        self.assertEqual(age, 601.0)
        fresh, age = base.radar_freshness({"capturedAt": "2026-09-03T10:32:00+08:00"}, now)
        self.assertFalse(fresh)
        self.assertEqual(age, -119.0)


if __name__ == "__main__":
    unittest.main()
