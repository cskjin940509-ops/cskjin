import copy
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
import selection_research_v46 as study
import selection_engine_v45 as engine
import run_ai_shadow_portfolio as base


class ForwardEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.fromisoformat('2026-09-04T10:20:00+08:00')
        self.state = {'selectionData45': {'sectorRanks': {'银行': {'complete': True, 'total': 2,
            'availableAt': self.now.isoformat(), 'rows': {
                '000001': {'price': 10., 'changePct': 0.}, '000002': {'price': 20., 'changePct': 2.}}}}}}
        self.targets = [{'code': '000001', 'name': '甲', 'sector': '银行', 'stage': 'EMERGING',
                         'rejections': ['等待买点'], 'referencePrice': 10}]
        self.radar = {'date': '2026-09-04', 'capturedAt': self.now.isoformat(), 'stocks': {
            '000001': {'marginData': {'dataDate': '2026-09-03', 'availableAt': '2026-09-04T08:00:00+08:00'}}}}
        self.quotes = {'000001': {'price': 10., 'quoteTime': self.now.isoformat()}}

    def freeze(self):
        study.freeze_candidates(self.state, self.targets, self.radar, self.quotes, self.now)
        return next(iter(self.state['research46']['cohorts'].values()))

    def test_first_observation_immutable_and_rejected_setup_still_observed(self):
        row = self.freeze(); original = copy.deepcopy(row)
        self.targets[0]['referencePrice'] = 30
        self.targets[0]['rejections'] = []
        self.freeze()
        self.assertEqual(row, original)
        self.assertEqual(row['frozen']['candidates'][0]['rejections'], ['等待买点'])
        self.assertEqual(study.pending_codes(self.state), {'000001', '000002'})

    def test_changed_protocol_never_pools_new_rules_with_old_frozen_samples(self):
        self.freeze()
        self.state['research46']['protocolHash'] = 'old-parameter-fingerprint'
        self.radar['capturedAt'] = self.now.isoformat()
        study.freeze_candidates(self.state, self.targets, self.radar, self.quotes, self.now)
        self.assertTrue(self.state['research46']['protocolChanged'])
        self.assertEqual(len(self.state['research46']['cohorts']), 1)

    def test_future_source_or_stale_radar_never_creates_freeze(self):
        self.state['selectionData45']['sectorRanks']['银行']['availableAt'] = (self.now + timedelta(minutes=1)).isoformat()
        study.freeze_candidates(self.state, self.targets, self.radar, self.quotes, self.now)
        self.assertEqual(self.state['research46']['cohorts'], {})
        self.state['selectionData45']['sectorRanks']['银行']['availableAt'] = self.now.isoformat()
        self.radar['capturedAt'] = (self.now - timedelta(minutes=20)).isoformat()
        study.freeze_candidates(self.state, self.targets, self.radar, self.quotes, self.now)
        self.assertEqual(self.state['research46']['cohorts'], {})

    def test_t_plus_one_without_publication_time_is_not_audit_pass(self):
        self.radar['stocks']['000001']['marginData'].pop('availableAt')
        self.freeze()
        audits = {x['id']: x for x in study.report(self.state, self.now)['audits']}
        self.assertEqual(audits['availableAt']['status'], 'MISSING')
        self.assertEqual(audits['frozen']['status'], 'CHECKED')

    def test_missing_former_member_blocks_result_and_tampering_is_detected(self):
        row = self.freeze()
        days = ['2026-09-07','2026-09-08','2026-09-09','2026-09-10','2026-09-11']
        self.state['selectionData45']['marketSessions'] = days
        now = datetime.fromisoformat('2026-09-11T15:10:00+08:00')
        q = {'000001': {'price': 11., 'quoteTime': '2026-09-11T15:00:00+08:00'}}
        study.mark_cohorts(self.state, q, now)
        self.assertEqual(row['outcomes'], {})
        self.assertIn('1只', row['pendingReasonZh'])
        q['000002'] = {'price': 18., 'quoteTime': '2026-09-11T15:00:00+08:00'}
        study.mark_cohorts(self.state, q, now)
        point = row['outcomes']['5']
        self.assertAlmostEqual(point['candidateReturnPct'], 10.)
        self.assertAlmostEqual(point['sectorEqualWeightReturnPct'], 0.)
        self.assertAlmostEqual(point['excessVsB0Pp'], 20.)
        row['frozen']['members']['000001'] = 1.
        study.mark_cohorts(self.state, q, now)
        self.assertFalse(row['integrityOk'])
        self.assertEqual(study.report(self.state, now)['audits'][-1]['status'], 'MISSING')

    def test_missing_horizon_is_not_backfilled_with_later_price(self):
        row = self.freeze()
        self.state['selectionData45']['marketSessions'] = ['2026-09-07','2026-09-08','2026-09-09','2026-09-10','2026-09-11','2026-09-14']
        now = datetime.fromisoformat('2026-09-14T15:10:00+08:00')
        q = {c: {'price': 11., 'quoteTime': '2026-09-14T15:00:00+08:00'} for c in ('000001','000002')}
        study.mark_cohorts(self.state, q, now)
        self.assertNotIn('5', row['outcomes'])

    def test_future_quote_never_counts_as_close(self):
        q = {'price': 11., 'quoteTime': '2026-09-04T15:30:00+08:00'}
        now = datetime.fromisoformat('2026-09-04T15:05:00+08:00')
        self.assertIsNone(study.quote_price(q, now, True))

    def test_many_correlated_stocks_do_not_become_many_signal_dates(self):
        row = self.freeze(); row['outcomes']['10'] = {'excessVsB0Pp': 5}; row['integrityOk'] = True
        for i in range(100):
            self.state['research46']['cohorts'][str(i)] = copy.deepcopy(row)
        summary = study.stage_summary(self.state['research46'])
        self.assertEqual(summary['matureSignalDates'], 1)
        self.assertEqual(summary['status'], 'COLLECTING')

    def test_waiting_and_pending_exit_have_explicit_plan(self):
        plan = study.entry_plan(self.targets[0]); self.assertIsNone(plan['buyZoneLow'])
        plan = study.holding_plan({}, {'reasonZh':'保护线触发'}, False)
        self.assertEqual(plan['actionZh'], '等待执行退出')
        self.assertEqual(study.holding_plan({}, None, False)['actionZh'], '等待新行情')


class NoTControlTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.fromisoformat('2026-09-04T10:20:00+08:00')
        self.clock = patch.object(base, 'now_cn', side_effect=lambda: self.now)
        self.clock.start(); self.addCleanup(self.clock.stop)
        self.state = base.new_state()
        self.state['positions'] = {'000001': {'code': '000001', 'name': '甲', 'sector': '银行',
            'qty': 1000, 'avgCost': 10., 'lastPrice': 10., 'entryDate': '2026-09-03', 'costAmount': 10000}}
        self.state['cash'] -= 10000
        self.prices = {'000001': 10.}; self.ledger = []
        engine.CONTEXT.clear(); engine.NO_T_CONTROL = False
        engine.start_no_t_control(self.state, self.ledger, self.prices)

    def test_no_t_book_starts_equal_and_is_independent(self):
        control = self.state['research46']['noTControl']
        self.assertEqual(control['state']['cash'], self.state['cash'])
        self.state['positions']['000001']['qty'] = 800
        self.assertEqual(control['state']['positions']['000001']['qty'], 1000)
        self.assertNotIn('research46', control['state'])
        simple = self.state['research46']['timingControl']
        self.assertEqual(simple['state']['positions']['000001']['qty'], 1000)
        control['state']['positions']['000001']['qty'] = 500
        self.assertEqual(simple['state']['positions']['000001']['qty'], 1000)

    def test_sell_fly_loss_is_in_full_portfolio_comparison_and_no_double_posting(self):
        # Actual sleeve sells 200 shares at 10, paying 5. Control retains all 1000.
        self.state['positions']['000001']['qty'] = 800
        self.state['cash'] += 1995
        self.now = datetime.fromisoformat('2026-09-04T15:10:00+08:00')
        self.prices['000001'] = 11.
        engine.CONTEXT['quotes'] = {'000001': {'price': 11., 'quoteTime': '2026-09-04T15:00:00+08:00'}}
        before = self.state['cash']; report = engine.update_no_t_control(self.state, self.ledger, self.prices, {}, True)
        initial = self.state['initialCapital']
        self.assertAlmostEqual(report['incrementalReturnPp'], -205 / initial * 100)
        self.assertEqual(self.state['cash'], before)
        again = engine.update_no_t_control(self.state, self.ledger, self.prices, {}, True)
        self.assertEqual(again['closeSampleDays'], 1)

    def test_control_has_same_inputs_and_disables_t_without_changing_global_mode(self):
        radar = {'date': '2026-09-04', 'capturedAt': self.now.isoformat(), 'stocks': {}}
        engine.CONTEXT['radar'] = radar
        def entries(book, ledger, data, prices):
            self.assertTrue(engine.NO_T_CONTROL)
            self.assertEqual(engine.evaluate_t(book, ledger, prices, data), [])
            book['cash'] -= 1
            return []
        with patch.object(engine, 'evaluate_exits', return_value=[]), patch.object(engine, 'evaluate_entries', side_effect=entries):
            engine.update_no_t_control(self.state, self.ledger, self.prices, radar, False)
        self.assertFalse(engine.NO_T_CONTROL)
        self.assertEqual(self.state['research46']['noTControl']['state']['cash'], self.state['cash'] - 1)

    def test_simple_holding_preserves_hard_risk_but_excludes_discretionary_exit(self):
        engine.CONTROL_MODE = 'FIXED_HOLD'
        self.addCleanup(setattr, engine, 'CONTROL_MODE', None)
        engine.CONTEXT['market'] = {'state': 'UNKNOWN', 'cap': 0, 'allowNew': False}
        engine.metadata(self.state)
        pos = self.state['positions']['000001']
        engine.queue_exit(self.state, pos, 1000, 'TRAIL_STOP', '移动止盈')
        self.assertEqual(self.state['selection45']['pendingExits'], {})
        engine.queue_exit(self.state, pos, 1000, 'HARD_STOP', '止损')
        self.assertEqual(self.state['selection45']['pendingExits']['000001']['reasonCode'], 'HARD_STOP')

    def test_fixed_holding_reaches_ten_sessions_and_queues_real_exit(self):
        engine.CONTROL_MODE = 'FIXED_HOLD'; engine.NO_T_CONTROL = True
        self.addCleanup(setattr, engine, 'CONTROL_MODE', None)
        self.addCleanup(setattr, engine, 'NO_T_CONTROL', False)
        self.state['positions']['000001']['entryDate'] = '2026-08-19'
        self.state['selectionData45'] = {'marketSessions': [
            '2026-08-20','2026-08-21','2026-08-24','2026-08-25','2026-08-26',
            '2026-08-27','2026-08-28','2026-08-31','2026-09-01','2026-09-02','2026-09-03']}
        quotes = {'000001': {'price': 10., 'quoteTime': self.now.isoformat(), 'amount': 1e8}}
        engine.CONTEXT.update(quotes=quotes, market={'state': 'UNKNOWN','cap': 0.,'allowNew': False},
            radar={'date': '2026-09-04', 'capturedAt': self.now.isoformat(), 'stocks': {}})
        base.EXECUTION_MARKET = {'000001': {'price': 10.,'prevClose': 10.,'amount': 1e8,'quoteTime': self.now.isoformat()}}
        actions = engine.evaluate_exits(self.state, self.ledger, {}, quotes, self.prices)
        pending = self.state['selection45']['pendingExits'].get('000001')
        self.assertTrue(any(x['reasonCode']=='FIXED_HOLD_EXIT' for x in actions) or (pending and pending['reasonCode']=='FIXED_HOLD_EXIT'))

    def test_comparison_does_not_join_different_closing_dates(self):
        a = {'statusZh': '已更新', 'closeSampleDays': 2, 'asOfDate': '2026-09-04', 'withoutTReturnPct': 2.}
        b = {'statusZh': '已更新', 'closeSampleDays': 1, 'asOfDate': '2026-09-03', 'withoutTReturnPct': 1.}
        result = study.report(self.state, self.now, a, b)['timingComparison']
        self.assertIsNone(result['incrementalReturnPp'])

    def test_missing_control_close_or_changed_capital_never_reports_comparison(self):
        self.now = datetime.fromisoformat('2026-09-04T15:10:00+08:00')
        report = engine.update_no_t_control(self.state, self.ledger, self.prices, {}, True)
        self.assertIsNone(report['incrementalReturnPp'])
        self.state['capitalEvents'] = [{'amount': 100000}]
        report = engine.update_no_t_control(self.state, self.ledger, self.prices, {}, True)
        self.assertIn('暂停对比', report['statusZh'])


if __name__ == '__main__': unittest.main()
