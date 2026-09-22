import os
import unittest
from unittest.mock import MagicMock, patch

import tushare_stock_api as api


class TushareStockApiTest(unittest.TestCase):
    def test_market_mapping(self):
        self.assertEqual(api.ts_code("600000"), "600000.SH")
        self.assertEqual(api.ts_code("000001"), "000001.SZ")
        self.assertEqual(api.ts_code("920087"), "920087.BJ")

    def test_no_credential_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                api._token()

    def test_realtime_normalization(self):
        frame = MagicMock()
        frame.empty = False
        frame.to_dict.return_value = [{
            "TS_CODE": "000001.SZ", "NAME": "平安银行", "PRICE": 10.2,
            "PRE_CLOSE": 10.0, "OPEN": 10.05, "HIGH": 10.3, "LOW": 9.99,
            "DATE": "20260922", "TIME": "09:45:01", "AMOUNT": 1234,
        }]
        pro = MagicMock(); pro.realtime_quote.return_value = frame
        with patch.object(api, "pro_api", return_value=pro):
            rows = api.realtime_quotes(["000001"])
        self.assertEqual(rows["000001"]["quoteTime"], "20260922094501")
        self.assertAlmostEqual(rows["000001"]["changePct"], 2.0)
        self.assertIn("Tushare", rows["000001"]["source"])


if __name__ == "__main__":
    unittest.main()
