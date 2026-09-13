import json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
import backfill_etf_485 as b

class ETFBackfillTests(unittest.TestCase):
    def test_compact_verified_calendar_is_preferred(self):
        with tempfile.TemporaryDirectory() as td:
            old=b.BACKFILL; b.BACKFILL=Path(td)
            try:
                dates=[f'{20240000+i:08d}' for i in range(490)]
                (Path(td)/'trading_dates.json').write_text(json.dumps({'tradeDates':dates}))
                self.assertEqual(b.trading_dates(), dates[-486:])
            finally: b.BACKFILL=old

    def test_existing_snapshot_requires_date_and_fields(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x.json'
            p.write_text(json.dumps({'data':{'fields':['ts_code','trade_date','fd_share'],
                'items':[[f'{i:06d}.SZ','20260911',1] for i in range(101)]}}))
            self.assertTrue(b.valid_existing(p,'20260911'))
            self.assertFalse(b.valid_existing(p,'20260910'))

    def test_window_has_predecessor(self):
        rows=[]
        for i in range(490):
            day=f'{20240000+i:08d}'
            rows += [[day,'SSE'],[day,'SZSE']]
        with tempfile.TemporaryDirectory() as td:
            old=b.BACKFILL; b.BACKFILL=Path(td)
            try:
                (Path(td)/'margin.json').write_text(json.dumps({'data':{
                    'fields':['trade_date','exchange_id'],'items':rows}}))
                self.assertEqual(len(b.trading_dates()),486)
            finally: b.BACKFILL=old

    def test_lfs_pointer_falls_back_to_api_calendar(self):
        rows=[]
        for i in range(490):
            day=f'{20240000+i:08d}'; rows += [[day,'SSE'],[day,'SZSE']]
        with tempfile.TemporaryDirectory() as td:
            old=b.BACKFILL; b.BACKFILL=Path(td)
            try:
                (Path(td)/'margin.json').write_text('version https://git-lfs.github.com/spec/v1')
                with patch.object(b,'request',return_value={
                    'fields':['cal_date'],'items':[[r[0]] for r in rows[::2]]}):
                    self.assertEqual(len(b.trading_dates()),486)
            finally: b.BACKFILL=old

if __name__=='__main__': unittest.main()
