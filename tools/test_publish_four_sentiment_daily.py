import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import tools.publish_four_sentiment_daily as mod


CN = timezone(timedelta(hours=8))


class DailySentimentTests(unittest.TestCase):
    def test_publishes_four_rows_and_never_turns_missing_into_zero(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "astock_snapshots").mkdir()
            (root / "astock_factors").mkdir()
            (root / "astock_snapshots" / "index.json").write_text(json.dumps({"snapshots": [{
                "date": "2026-09-09", "status": "Official", "marketSnapshot": {
                    "sourceDate": "2026-09-09", "availableAt": "2026-09-09T17:00:00+08:00",
                    "up": 1729, "down": 3369, "flat": 111, "sampleCount": 5209}}]}))
            (root / "astock_factors" / "latest.json").write_text(json.dumps({
                "collectedAt": "2026-09-10T08:30:00+08:00",
                "margin": {"dataDate": "2026-09-09", "marketSummary": {
                    "complete": False, "financingBalance": None, "exchangeCoverage": ["BSE"]}},
                "etf": {"dataDate": "2026-09-09", "tradingDates": ["a"], "etfs": {}}}))
            with patch.object(mod, "ROOT", root), patch.object(mod, "OUT", root / "astock_sentiment"), \
                 patch.object(mod, "HISTORY", root / "astock_sentiment" / "history"):
                out = mod.publish(datetime(2026, 9, 10, 9, 0, tzinfo=CN))
            self.assertEqual(len(out["indices"]), 4)
            self.assertTrue(all(x["score"] is None for x in out["indices"]))
            self.assertAlmostEqual(out["indices"][0]["raw"]["logUpDownRatio"], -0.6669320160)
            self.assertFalse(out["positionControlEnabled"])
            self.assertTrue((root / "astock_sentiment" / "history" / "2026-09-10.json").exists())


if __name__ == "__main__": unittest.main()
