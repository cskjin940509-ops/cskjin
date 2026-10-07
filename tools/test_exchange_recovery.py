import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
import astock_calendar as calendar
import augment_trade_plan_market_setups as scan
import run_tail_rolling_reliable as tail
import publish_data_on_arrival as publish

CN=timezone(timedelta(hours=8))
class RecoveryTests(unittest.TestCase):
    def test_exchange_holidays_and_makeup_weekends(self):
        for day in ('2026-10-07','2026-09-25','2026-10-10','2026-02-23'):
            self.assertFalse(calendar.is_trading_day(day))
        self.assertTrue(calendar.is_trading_day('2026-10-08'))
    def test_unknown_calendar_fails_closed(self):
        with self.assertRaises(RuntimeError): calendar.is_trading_day('2027-01-04')
    def test_holiday_does_not_dispatch_trading(self):
        self.assertEqual(publish.targets('gateway',datetime(2026,10,7,15,10,tzinfo=CN)),())
    def test_holiday_tail_never_requests_prices(self):
        with patch.object(tail,'datetime') as clock, patch.object(tail.rolling.core,'current_index_payload') as quotes:
            clock.now.return_value=datetime(2026,10,7,22,tzinfo=CN)
            with patch.object(tail.rolling,'datetime') as inner:
                inner.now.return_value=clock.now.return_value
                tail.main()
            quotes.assert_not_called()
    def test_empty_market_response_is_failure(self):
        with patch.object(scan.base,'get_json',return_value={'data':{'total':5000,'diff':[]}}):
            with self.assertRaises(RuntimeError): scan.market_page(1)
    def test_source_outage_persists_block_and_clears_candidates(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'latest.json'
            path.write_text(json.dumps({'date':'2026-10-08','phase':'LIVE','setupCandidates':[{'code':'old'}]}))
            with patch.object(scan,'OUT',path),patch.object(scan,'datetime') as clock,patch.object(scan,'all_a_rows',side_effect=RuntimeError('502')),patch.object(scan.time,'sleep'):
                clock.now.return_value=datetime(2026,10,8,10,tzinfo=CN)
                with self.assertRaises(RuntimeError): scan.main()
            result=json.loads(path.read_text())
            self.assertEqual(result['setupCandidates'],[])
            self.assertEqual(result['marketSetupScan']['state'],'blocked')

if __name__=='__main__': unittest.main()
