import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_ai_shadow_contract as contract


class PortfolioReconciliationTests(unittest.TestCase):
    def test_partial_exit_and_full_exit_reconcile(self):
        fills = [
            {"code": "000001", "side": "BUY", "qty": 300},
            {"code": "000001", "side": "SELL", "qty": 100},
            {"code": "000002", "side": "BUY", "qty": 100},
            {"code": "000002", "side": "SELL", "qty": 100},
        ]
        contract.validate_ledger_positions(fills, {"000001": {"qty": 200}})
        with self.assertRaisesRegex(AssertionError, "reconcile"):
            contract.validate_ledger_positions(fills, {"000001": {"qty": 300}})

    def test_oversell_is_rejected(self):
        with self.assertRaisesRegex(AssertionError, "sells more"):
            contract.validate_ledger_positions(
                [{"code": "000001", "side": "SELL", "qty": 100}], {})


if __name__ == "__main__":
    unittest.main()
