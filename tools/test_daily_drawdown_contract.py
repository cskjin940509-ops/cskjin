import copy
import unittest
from tools.validate_ai_shadow_contract import validate_daily_drawdown


class DrawdownContractTests(unittest.TestCase):
    def payload(self):
        return {"summary": {"formalCloseSampleDays": 2, "dailyCloseDrawdownStatus": "VALID", "maxDrawdownPct": -1.0},
                "dailyPerformance": [{"date": "2026-09-03", "closeUnitNav": 1.0},
                                     {"date": "2026-09-04", "closeUnitNav": .99}],
                "performanceReport": {"risk": {"dailyCloseMaxDrawdownPct": -1.0}}}

    def test_verified_drawdown_recomputed(self):
        self.assertEqual(validate_daily_drawdown(self.payload()), [])

    def test_missing_nan_or_wrong_drawdown_rejected_with_samples(self):
        for value in (None, float('nan'), 0, -2):
            with self.subTest(value=value), self.assertRaises(AssertionError):
                data = self.payload()
                data['summary']['maxDrawdownPct'] = value
                validate_daily_drawdown(data)

    def test_no_samples_is_warning_not_green_or_fake_zero(self):
        data = self.payload()
        data['dailyPerformance'] = []
        data['summary'].update(formalCloseSampleDays=0, dailyCloseDrawdownStatus='MISSING_VERIFIED_CLOSES', maxDrawdownPct=None)
        data['performanceReport']['risk']['dailyCloseMaxDrawdownPct'] = None
        self.assertTrue(validate_daily_drawdown(data))
        data['summary']['maxDrawdownPct'] = 0
        with self.assertRaises(AssertionError):
            validate_daily_drawdown(data)

    def test_duplicate_dates_or_count_mismatch_rejected(self):
        data = self.payload()
        data['dailyPerformance'][1]['date'] = '2026-09-03'
        with self.assertRaises(AssertionError):
            validate_daily_drawdown(data)
        data = self.payload()
        data['summary']['formalCloseSampleDays'] = 0
        with self.assertRaises(AssertionError):
            validate_daily_drawdown(data)
