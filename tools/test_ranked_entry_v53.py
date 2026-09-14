"""Exercise actual simulated fills on synthetic inputs; never touch production books."""
import sys
import unittest
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_selection_v45 as fixtures
import selection_engine_v45 as engine
from execution_status_v48 import explain


class RankedEntryTests(unittest.TestCase):
    refresh = fixtures.SelectionTests.refresh

    def setUp(self):
        fixtures.SelectionTests.setUp(self)
        engine.NO_T_CONTROL = False
        engine.CONTROL_MODE = None
        self.state['positions'] = {}
        self.state['cash'] = self.state['initialCapital']
        self.now = self.now.replace(hour=9, minute=40)
        self.refresh()
        engine.CONTEXT['market'].update(cap=.5, baseCap=.5)
        stock = engine.CONTEXT['radar']['stocks']['000001']
        stock.update(earlyEntryScore=40, mainlineFormationScore=50, changePct=1.,
                     chaseRisk='LOW', yunai={'quoteOk': False})
        engine.CONTEXT['radar']['mainlines'][0]['mainFlowPct'] = 2.
        self.state['selectionData45']['technical']['000001'] = {'ready': False}
        engine.CONTEXT['quotes']['000001']['changePct'] = 1.

    def entries(self):
        return engine.evaluate_entries(self.state, self.ledger, engine.CONTEXT['radar'], self.prices)

    def test_first_fresh_tick_buys_despite_low_score_and_missing_history(self):
        rows = self.entries()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['side'], 'BUY')
        target = engine.LAST_TARGETS[0]
        self.assertLess(target['score'], 64)
        self.assertEqual(target['rejections'], [])
        self.assertEqual(target['targetWeight'], .01)
        self.assertEqual(target['decisionPlan']['actionZh'], '本轮已模拟买入')
        self.assertEqual(self.state['positions']['000001']['hardStopPrice'] > 0, True)
        nav, mv = engine.base.portfolio_nav(self.state, self.prices)
        self.assertLessEqual(mv / nav, .01)
        report = explain({'selection45': {'candidates': engine.LAST_TARGETS}})
        self.assertEqual(report['reasonCode'], 'ENTRY_FILLED')
        count = len(self.ledger)
        self.entries()
        self.assertEqual(len(self.ledger), count)

    def test_zero_market_budget_never_buys(self):
        engine.CONTEXT['market'].update(cap=0, allowNew=False)
        self.assertEqual(self.entries(), [])
        self.assertEqual(self.ledger, [])

    def test_stale_quote_does_not_become_ranked_fill(self):
        engine.CONTEXT['quotes']['000001']['quoteTime'] = (self.now - timedelta(minutes=8)).isoformat()
        self.assertEqual(self.entries(), [])

    def test_absent_liquidity_keeps_candidate_and_reports_actual_execution_gap(self):
        engine.base.EXECUTION_MARKET['000001']['amount'] = None
        engine.CONTEXT['quotes']['000001']['amount'] = None
        self.assertEqual(self.entries(), [])
        target = engine.LAST_TARGETS[0]
        self.assertEqual(target['rejections'], [])
        self.assertIn('累计成交额', target['executionReasonZh'])

    def test_no_fill_during_lunch_or_after_entry_session(self):
        for hour, minute in ((12, 10), (14, 55), (15, 20)):
            self.now = self.now.replace(hour=hour, minute=minute)
            engine.CONTEXT['radar']['capturedAt'] = self.now.isoformat()
            engine.CONTEXT['quotes']['000001']['quoteTime'] = self.now.isoformat()
            self.assertEqual(self.entries(), [])

    def test_all_observed_negative_funding_remains_risk_rejection(self):
        engine.CONTEXT['radar']['mainlines'][0]['mainFlowPct'] = -2.
        self.assertEqual(self.entries(), [])
        self.assertIn('已取得的板块资金证据均不支持买入', engine.LAST_TARGETS[0]['rejections'])

    def test_ranked_preferences_are_idempotent_and_keep_explicit_risks(self):
        target = {'score': 60, 'targetWeight': .04, 'rejections': [
            '综合分不足64', '未确认回撤企稳/突破回踩，继续等待', '风险警示/退市/停牌禁止买入']}
        engine.apply_ranked_entry_policy(target)
        once = deepcopy(target)
        engine.apply_ranked_entry_policy(target)
        self.assertEqual(target, once)
        self.assertEqual(target['rejections'], ['风险警示/退市/停牌禁止买入'])


if __name__ == '__main__':
    unittest.main()
