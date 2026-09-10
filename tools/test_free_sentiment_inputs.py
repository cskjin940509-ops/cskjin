import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_slow_money_factors_v2 as collector


class Frame:
    def __init__(self, rows): self.rows = rows; self.empty = not rows
    def where(self, *_): return self
    def to_dict(self, *_): return self.rows


class FreeSentimentInputTests(unittest.TestCase):
    def test_full_exchange_summary_is_separate_and_not_score_ready(self):
        with patch.object(collector.ak, "stock_margin_sse", return_value=Frame([{"融资余额": 10_000_000_000}])), \
             patch.object(collector.ak, "stock_margin_szse", return_value=Frame([{"融资余额": 80.0}])), \
             patch.object(collector.ak, "stock_margin_detail_bse", return_value=Frame([{"融资余额": 2_000_000}, {"融资余额": 3_000_000}])):
            result = collector.fetch_market_margin_summary(date(2026, 9, 9))
        self.assertTrue(result["complete"])
        self.assertEqual(result["financingBalance"], 18_005_000_000)
        self.assertFalse(result["scoreEligible"])

    def test_partial_exchange_data_never_becomes_market_total(self):
        with patch.object(collector.ak, "stock_margin_sse", side_effect=RuntimeError()), \
             patch.object(collector.ak, "stock_margin_szse", return_value=Frame([{"融资余额": 80.0}])), \
             patch.object(collector.ak, "stock_margin_detail_bse", return_value=Frame([{"融资余额": 2_000_000}])):
            result = collector.fetch_market_margin_summary(date(2026, 9, 9))
        self.assertFalse(result["complete"])
        self.assertIsNone(result["financingBalance"])
        self.assertEqual(result["scoreBlocker"], "交易所覆盖不完整")


if __name__ == "__main__": unittest.main()
