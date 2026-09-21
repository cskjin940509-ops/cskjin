import unittest
from datetime import datetime
from unittest.mock import patch
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import batch_execution_v6 as batch
import selection_engine_v45 as engine
import test_selection_v45 as fixtures


class BatchExecutionV6Tests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.SelectionTests(methodName='test_file_sentiment_position_table')
        self.fx.setUp()
        self.addCleanup(self.fx.tearDown)
        self.state, self.ledger, self.prices = self.fx.state, self.fx.ledger, self.fx.prices
        self.radar = engine.CONTEXT['radar']
        self.state['positions'] = {}
        self.state['cash'] = self.state['initialCapital']

    def test_close_freezes_but_never_buys_same_day(self):
        self.fx.now = datetime.fromisoformat('2026-09-04T15:05:00+08:00')
        self.radar['date'] = '2026-09-04'; self.radar['capturedAt'] = self.fx.now.isoformat()
        for quote in engine.CONTEXT['quotes'].values(): quote['quoteTime'] = self.fx.now.isoformat()
        frozen = batch.freeze_signal(engine, self.state, self.radar, self.prices)
        self.assertIsNotNone(frozen)
        self.assertTrue(self.state['batchExecutionV6']['pendingOrders'])
        self.assertEqual(batch.evaluate_entries(engine, self.state, self.ledger, self.radar, self.prices), [])

    def test_t_plus_one_limit_buy_and_no_same_day_fill(self):
        self.fx.now = datetime.fromisoformat('2026-09-04T15:05:00+08:00')
        self.radar['date'] = '2026-09-04'; self.radar['capturedAt'] = self.fx.now.isoformat()
        for quote in engine.CONTEXT['quotes'].values(): quote['quoteTime'] = self.fx.now.isoformat()
        batch.freeze_signal(engine, self.state, self.radar, self.prices)
        self.state['positions'] = {}; self.state['cash'] = self.state['initialCapital']
        order = self.state['batchExecutionV6']['pendingOrders'][0]
        self.fx.now = datetime.fromisoformat('2026-09-07T10:00:00+08:00')
        self.radar['date'] = '2026-09-07'; self.radar['capturedAt'] = self.fx.now.isoformat()
        q = engine.CONTEXT['quotes'][order['code']]
        q['price'] = order['limitPrice'] * .999; q['quoteTime'] = self.fx.now.isoformat()
        engine.base.EXECUTION_MARKET[order['code']]['price'] = q['price']
        engine.CONTEXT['market'].update(cap=.5, allowNew=True)
        rows = batch.evaluate_entries(engine, self.state, self.ledger, self.radar, self.prices)
        self.assertEqual(len(rows), 1); self.assertEqual(rows[0]['side'], 'BUY')
        self.assertIn(order['code'], self.state['positions'])

    def test_ninth_signal_marks_oldest_fifo_exit(self):
        for i in range(8):
            self.state.setdefault('batchExecutionV6', batch.book(self.state))['batches'].append({
                'id': f'old{i}', 'sequence': i + 1, 'signalDate': f'2026-08-{20+i:02d}',
                'status': 'ACTIVE', 'lots': {'000001': 100 if i == 0 else 0}})
        self.fx.now = datetime.fromisoformat('2026-09-04T15:05:00+08:00')
        self.radar['date'] = '2026-09-04'; self.radar['capturedAt'] = self.fx.now.isoformat()
        for quote in engine.CONTEXT['quotes'].values(): quote['quoteTime'] = self.fx.now.isoformat()
        batch.freeze_signal(engine, self.state, self.radar, self.prices)
        self.assertEqual(self.state['batchExecutionV6']['batches'][0]['status'], 'PENDING_FIFO_EXIT')
        self.assertEqual(self.state['batchExecutionV6']['pendingExits'][0]['reasonCode'], 'FIFO_BATCH_EXPIRY')

    def test_stale_stored_signal_rebuilds_from_same_day_closing_radar(self):
        self.fx.now = datetime.fromisoformat('2026-09-04T15:05:00+08:00')
        self.radar['date'] = '2026-09-04'
        self.radar['capturedAt'] = '2026-09-04T14:55:00+08:00'
        stale = {'code': '000001', 'dataAt': '2026-09-03T15:00:00+08:00',
                 'rejections': [], 'rankingScore': 99, 'score': 99,
                 'referencePrice': 10., 'name': '旧候选', 'sector': '银行'}
        frozen = batch.freeze_signal(engine, self.state, self.radar, self.prices, [stale])
        self.assertIsNotNone(frozen)
        order = self.state['batchExecutionV6']['pendingOrders'][0]
        self.assertEqual(order['signalDate'], '2026-09-04')
        self.assertEqual(order['name'], '测试')

    def test_reopened_limit_up_is_not_treated_as_one_price_board(self):
        engine.base.EXECUTION_MARKET['000001'].update(
            price=11., open=11., low=10.5, upperLimit=11.)
        self.assertFalse(batch._market_limit_up(engine, '000001'))
        engine.base.EXECUTION_MARKET['000001']['low'] = 11.
        self.assertTrue(batch._market_limit_up(engine, '000001'))

    def test_intraday_low_touch_fills_at_limit_even_after_rebound(self):
        self.fx.now = datetime.fromisoformat('2026-09-04T15:05:00+08:00')
        self.radar['date'] = '2026-09-04'; self.radar['capturedAt'] = self.fx.now.isoformat()
        batch.freeze_signal(engine, self.state, self.radar, self.prices)
        order = self.state['batchExecutionV6']['pendingOrders'][0]
        self.fx.now = datetime.fromisoformat('2026-09-07T10:00:00+08:00')
        q = engine.CONTEXT['quotes'][order['code']]
        q.update(price=order['limitPrice'] * 1.01, low=order['limitPrice'] * .999,
                 quoteTime=self.fx.now.isoformat())
        engine.base.EXECUTION_MARKET[order['code']].update(
            price=q['price'], low=q['low'])
        engine.CONTEXT['market'].update(cap=.5, allowNew=True)
        rows = batch.evaluate_entries(engine, self.state, self.ledger, self.radar, self.prices)
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]['referencePrice'], order['limitPrice'], places=4)


if __name__ == '__main__':
    unittest.main()
