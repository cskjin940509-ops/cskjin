import copy
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_ai_shadow_portfolio as base
import run_ai_dynamic_portfolio_v2 as execution
import selection_engine_v45 as engine
import selection_rules_v45 as rules


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.fromisoformat('2026-09-04T10:20:00+08:00')
        self.clock = patch.object(base, 'now_cn', side_effect=lambda: self.now)
        self.clock.start(); self.addCleanup(self.clock.stop)
        self.state = base.new_state()
        self.state['positions'] = {'000001': {'code': '000001', 'name': '测试', 'sector': '银行',
            'qty': 10000, 'avgCost': 10., 'costAmount': 100000., 'entryPrice': 10.,
            'entryDate': '2026-08-28', 'dailyBuyQty': {}, 'lastPrice': 10., 'buyScore': 75.}}
        self.state['cash'] = self.state['initialCapital'] - 100000
        self.state['navHistory'] = [{'date': '2026-09-03', 'time': '15:00:00',
            'timestamp': '2026-09-03T15:00:00+08:00', 'nav': self.state['initialCapital'], 'isVerifiedClose': True}]
        self.state['selectionData45'] = {'marketSessions': ['2026-08-28', '2026-08-31', '2026-09-01', '2026-09-02', '2026-09-03'],
            'technical': {'000001': {'ready': True, 'atr14': .3, 'ma20': 10., 'high20': 12., 'low20': 8.,
            'previousHigh20': 11.8, 'return5Pct': 1., 'slope20Pct': 0., 'adv20': 1e9, 'volumeRatio5to20': 1.5}}}
        self.ledger = []; self.prices = {'000001': 10.}
        engine.CONTEXT.clear(); engine.LAST_ACTIONS = []; engine.LAST_TARGETS = []
        self.refresh()
        engine.metadata(self.state)

    def refresh(self, price=None):
        price = price or self.prices['000001']
        engine.CONTEXT.update(market={'state': 'NEUTRAL', 'cap': .6, 'allowNew': True},
            radar={'date': self.now.date().isoformat(), 'mainlines': [{'name': '银行', 'stage': 'CONFIRMING', 'changePct': .2, 'breadthPct': 70}],
                   'stocks': {'000001': {'code': '000001', 'name': '测试', 'sector': '银行', 'price': price,
                     'mainFlowPct': 2, 'yunai': {'quoteOk': True, 'price': price, 'quoteTime': self.now.isoformat()}}}},
            quotes={'000001': {'price': price, 'prevClose': 10., 'quoteTime': self.now.strftime('%Y%m%d%H%M%S'),
                              'amount': 1e9, 'volumeShares': 1e8}})
        self.prices['000001'] = price
        base.EXECUTION_MARKET = {'000001': {'price': price, 'prevClose': 10., 'amount': 1e9, 'quoteTime': self.now.isoformat()}}

    def exits(self):
        return engine.evaluate_exits(self.state, self.ledger, {}, engine.CONTEXT['quotes'], self.prices)

    def test_off_radar_never_forces_next_day_exit(self):
        engine.CONTEXT['radar']['stocks'] = {}
        for i in range(8):
            self.assertEqual(self.exits(), [])
        self.assertEqual(self.state['positions']['000001']['qty'], 10000)

    def test_hard_stop_pending_survives_t1_and_partial_capacity(self):
        pos = self.state['positions']['000001']
        pos.update(entryDate='2026-09-04', dailyBuyQty={'2026-09-04': 10000})
        self.refresh(9.4)
        self.assertEqual(self.exits(), [])
        self.assertEqual(self.state['selection45']['pendingExits']['000001']['state'], 'WAIT_T_PLUS_ONE')
        self.now = datetime.fromisoformat('2026-09-07T09:35:00+08:00'); self.refresh(9.4)
        base.EXECUTION_MARKET['000001']['amount'] = 1e6
        self.assertEqual(len(self.exits()), 1)
        self.assertGreater(self.state['selection45']['pendingExits']['000001']['remainingQty'], 0)
        self.assertLess(self.ledger[0]['qty'], 10000)

    def test_limit_down_no_assumed_stop_fill(self):
        self.refresh(9.)
        self.assertEqual(self.exits(), [])
        self.assertIn('000001', self.state['selection45']['pendingExits'])

    def test_no_risk_sale_using_stale_held_quote(self):
        self.refresh(9.4)
        self.now += timedelta(minutes=10)
        self.assertEqual(self.exits(), [])
        self.assertEqual(self.state['positions']['000001']['qty'], 10000)

    def test_two_daily_failures_trim_once_not_every_cycle(self):
        self.state['selection45']['holdingSignals'] = {'000001': {'daily': {
            '2026-09-02': {'stockInvalid': True}, '2026-09-03': {'stockInvalid': True}}}}
        first = self.exits(); second = self.exits()
        self.assertEqual(len(first), 1); self.assertEqual(second, [])
        self.assertEqual(self.state['positions']['000001']['qty'], 5000)

    def test_missing_trading_day_breaks_invalid_streak(self):
        self.state['selection45']['holdingSignals'] = {'000001': {'daily': {
            '2026-09-01': {'stockInvalid': True}, '2026-09-03': {'stockInvalid': True}}}}
        self.assertEqual(self.exits(), [])
        self.assertEqual(self.state['positions']['000001']['invalidDayStreak'], 1)

    def test_normal_exit_waits_window_but_hard_stop_does_not(self):
        self.now = self.now.replace(hour=11); self.refresh()
        pos = self.state['positions']['000001']
        engine.queue_exit(self.state, pos, 5000, 'STOCK_INVALID_2D', '连续失效')
        self.assertEqual(engine.execute_pending(self.state, self.ledger, self.prices), [])
        engine.queue_exit(self.state, pos, 10000, 'HARD_STOP', '止损')
        self.assertEqual(len(engine.execute_pending(self.state, self.ledger, self.prices)), 1)

    def test_t_plus_one_rebuy_cannot_be_resold(self):
        pos = self.state['positions']['000001']
        sale = execution.reduce_or_sell(self.state, self.ledger, pos, 2000, 10., 0, 'T')
        t = dict(code='000001', name='测试', sector='银行', referencePrice=9.9, score=75,
                 priceSource='test', reasonZh='T', targetWeight=.01, targetWeightPct=1)
        pos['invalidationZh'] = ''; pos['expectedHorizonZh'] = ''
        buy = execution.add_or_buy(self.state, self.ledger, t, 2000, self.prices, 'T')
        self.assertIsNotNone(sale); self.assertIsNotNone(buy)
        self.assertEqual(execution.sellable_qty(pos, '2026-09-04'), 8000)

    def test_atr_stop_never_widens(self):
        pos = self.state['positions']['000001']
        pos.update(rules.stop_lines(pos, 10.5, {'ready': True, 'atr14': .1}))
        first = pos['hardStopPrice']
        pos.update(rules.stop_lines(pos, 10.2, {'ready': True, 'atr14': 2.}))
        self.assertEqual(pos['hardStopPrice'], first)

    def test_today_and_future_daily_bars_excluded(self):
        bars = [{'date': (self.now.date() - timedelta(days=30-i)).isoformat(), 'high': 11., 'low': 9., 'close': 10., 'amount': 1e8} for i in range(30)]
        a = rules.indicators(bars, self.now)
        bars += [{'date': self.now.date().isoformat(), 'high': 1000., 'low': 1., 'close': 900., 'amount': 1e12}]
        self.assertEqual(a, rules.indicators(bars, self.now))

    def test_same_day_margin_cannot_confirm(self):
        stock = {'marginData': {'dataDate': '2026-09-04', 'balanceChange1d': 1e8}}
        self.assertNotIn('B1', rules.sector_evidence(stock, {}, '2026-09-04'))

    def test_missing_breadth_blocks_buy_without_forcing_liquidation(self):
        market = rules.market_regime({'sourceDate': '2026-09-04', 'verifiedToday': True,
            'availableAt': self.now.isoformat(), 'indices': {k: {'changePct': 0} for k in ('sh000001', 'sh000300', 'sz399006')}}, self.now)
        engine.CONTEXT['market'] = market
        r = engine.risk_control(self.state, self.prices)
        self.assertFalse(r['allowNew']); self.assertFalse(r['forceReduction'])

    def test_no_intraday_mark_as_formal_close(self):
        self.state['navHistory'][0].pop('isVerifiedClose')
        self.assertFalse(engine.risk_control(self.state, self.prices)['allowNew'])

    def test_t_cost_gap_trend_gates(self):
        tech = self.state['selectionData45']['technical']['000001']
        samples = [{'at': '2026-09-04T10:10:00+08:00', 'price': 10.3, 'vwap': 10},
                   {'at': '2026-09-04T10:15:00+08:00', 'price': 10.5, 'vwap': 10},
                   {'at': '2026-09-04T10:20:00+08:00', 'price': 10.4, 'vwap': 10}]
        self.assertTrue(rules.t_signal(10.4, tech, samples, 1.)['eligible'])
        self.assertFalse(rules.t_signal(10.4, dict(tech, slope20Pct=2), samples, 1.)['eligible'])
        self.assertFalse(rules.t_signal(10.4, tech, samples, 4.)['eligible'])
        samples[0]['at'] = '2026-09-04T09:50:00+08:00'
        self.assertFalse(rules.t_signal(10.4, tech, samples, 1.)['eligible'])

    def test_unpaired_sold_away_loss_included_without_double_nav(self):
        before = copy.deepcopy(self.state)
        self.state['selection45']['tCycles'] = [{'id': 'T', 'code': '000001', 'status': 'UNPAIRED',
            'soldQty': 1000, 'remainingQty': 1000, 'boughtQty': 0, 'sellNetProceeds': 9990.,
            'buyCost': 0., 'realizedPairPnl': 0., 'fees': 10.}]
        report = engine.t_report(self.state, {'000001': 11.})
        self.assertEqual(report['incrementalPnlVsUnchangedShares'], -1010.)
        self.assertEqual(before['cash'], self.state['cash'])
        self.assertEqual(before['positions'], self.state['positions'])

    def test_no_new_entries_outside_window_even_with_signals(self):
        self.now = self.now.replace(hour=11); self.refresh()
        candidate = {'code': '000001', 'name': '测试', 'sector': '银行', 'score': 80, 'referencePrice': 10.,
            'rejections': [], 'targetWeight': .08, 'targetWeightPct': 8., 'priceSource': 'test', 'reasonZh': 'test'}
        with patch.object(engine, 'build_candidate', return_value=candidate):
            for _ in range(4):
                engine.evaluate_entries(self.state, self.ledger, engine.CONTEXT['radar'], self.prices)
                self.now += timedelta(minutes=5); self.refresh()
        self.assertEqual(self.ledger, [])

    def test_repeated_snapshot_is_not_three_confirmations(self):
        candidate = {'code': '000001', 'name': '测试', 'sector': '银行', 'score': 80, 'referencePrice': 10.,
            'rejections': [], 'targetWeight': .08, 'targetWeightPct': 8., 'priceSource': 'test', 'reasonZh': 'test'}
        with patch.object(engine, 'build_candidate', return_value=candidate):
            for _ in range(4): engine.evaluate_entries(self.state, self.ledger, engine.CONTEXT['radar'], self.prices)
        self.assertEqual(self.ledger, [])
        self.assertEqual(self.state['selection45']['confirmations']['000001']['count'], 1)

    def test_actual_t_pair_cost_and_daily_limit(self):
        pos = self.state['positions']['000001']; pos['completeObservedDays'] = 4
        pos['invalidationZh'] = 'test'; pos['expectedHorizonZh'] = 'test'
        self.refresh(10.4)
        self.state['selection45']['samples'] = {'000001': [
            {'at': '2026-09-04T10:10:00+08:00', 'price': 10.3, 'vwap': 10.},
            {'at': '2026-09-04T10:15:00+08:00', 'price': 10.5, 'vwap': 10.}]}
        first = engine.evaluate_t(self.state, self.ledger, self.prices, engine.CONTEXT['radar'])
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]['reasonCode'], 'T_SELL_FIRST')
        self.assertEqual(first[0]['qty'], 2000)
        self.now = self.now.replace(minute=40); self.refresh(9.95)
        self.state['selection45']['samples']['000001'] = [
            {'at': '2026-09-04T10:30:00+08:00', 'price': 9.9, 'vwap': 10.},
            {'at': '2026-09-04T10:35:00+08:00', 'price': 9.9, 'vwap': 10.}]
        buy = engine.evaluate_t(self.state, self.ledger, self.prices, engine.CONTEXT['radar'])
        self.assertEqual(len(buy), 1)
        self.assertEqual(buy[0]['reasonCode'], 'T_BUYBACK')
        cycle = self.state['selection45']['tCycles'][0]
        self.assertEqual(cycle['status'], 'PAIRED')
        expected = first[0]['amount'] - first[0]['fee'] - buy[0]['amount'] - buy[0]['fee']
        self.assertAlmostEqual(cycle['realizedPairPnl'], expected, places=2)
        self.assertEqual(execution.sellable_qty(pos, '2026-09-04'), 8000)
        self.assertEqual(engine.evaluate_t(self.state, self.ledger, self.prices, engine.CONTEXT['radar']), [])


if __name__ == '__main__':
    unittest.main()
