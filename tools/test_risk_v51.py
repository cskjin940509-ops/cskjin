import sys, unittest, json
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
from copy import deepcopy
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_selection_v45 as fixtures
import selection_engine_v45 as engine
import selection_rules_v45 as rules
import collect_selection_evidence_v51 as collector
import publish_data_on_arrival as arrival
import yunai_tail_overlay as overlay

class IndependentRiskTests(unittest.TestCase):
    refresh = fixtures.SelectionTests.refresh
    def setUp(self):
        fixtures.SelectionTests.setUp(self)
        engine.CONTROL_MODE=None;engine.NO_T_CONTROL=False
        self.now=self.now.replace(hour=9,minute=40)
        fixtures.SelectionTests.refresh(self)
    def defense(self):
        engine.CONTEXT.update(market={'state':'DEFENSIVE','cap':.25,'allowNew':True},marketAt=self.now.isoformat())
    def full(self):
        self.state['positions']['000001']['qty']=int(self.state['initialCapital']/10)
        self.state['positions']['000001']['costAmount']=self.state['initialCapital']
        self.state['cash']=0.
    def exits(self):return engine.evaluate_exits(self.state,self.ledger,{},engine.CONTEXT['quotes'],self.prices)
    def test_defense_distinct_snapshots_and_restart(self):
        self.full();self.defense()
        for _ in range(4):self.assertFalse(engine.risk_control(self.state,self.prices)['forceReduction'])
        self.state=json.loads(json.dumps(self.state))
        self.now+=timedelta(seconds=60);self.defense()
        r=engine.risk_control(self.state,self.prices)
        self.assertTrue(r['forceReduction']);self.assertFalse(r['allowNew'])
    def test_defense_ignores_window_holding_age_and_normal_turnover(self):
        self.full();self.defense();engine.risk_control(self.state,self.prices)
        self.state['positions']['000001']['entryDate']='2026-09-03'
        self.now+=timedelta(seconds=60);fixtures.SelectionTests.refresh(self);self.defense()
        with patch.object(engine,'turnover_room',return_value=0):
            rows=self.exits()
        self.assertTrue(rows)
        self.assertEqual(rows[0]['reasonCode'],'PORTFOLIO_RISK')
        self.assertLess(self.state['positions']['000001']['qty'],int(self.state['initialCapital']/10))
    def test_defense_t1_persists_unfilled_quantity(self):
        self.full();self.defense();engine.risk_control(self.state,self.prices)
        self.now+=timedelta(seconds=60);fixtures.SelectionTests.refresh(self);self.defense()
        self.state['positions']['000001']['dailyBuyQty']={self.now.date().isoformat():int(self.state['initialCapital']/10)}
        self.assertEqual(self.exits(),[])
        self.assertEqual(self.state['selection45']['pendingExits']['000001']['state'],'WAIT_T_PLUS_ONE')
    def test_defense_reset_on_recovery_and_old_snapshot_not_counted(self):
        self.full();self.defense();engine.risk_control(self.state,self.prices)
        engine.CONTEXT['market']={'state':'NEUTRAL','cap':.6,'allowNew':True}
        engine.risk_control(self.state,self.prices)
        self.now+=timedelta(seconds=60);self.defense()
        self.assertFalse(engine.risk_control(self.state,self.prices)['forceReduction'])
        self.now+=timedelta(minutes=20)
        self.assertFalse(engine.risk_control(self.state,self.prices)['forceReduction'])
    def test_stale_radar_still_runs_real_stop_but_never_entries(self):
        fixtures.SelectionTests.refresh(self,9.4)
        radar={'date':'2026-09-03','capturedAt':'2026-09-03T15:00:00+08:00','stocks':{}}
        engine.CONTEXT['radar']=radar
        with patch.object(engine.base,'evaluate_exits',side_effect=engine.evaluate_exits),patch.object(engine.base,'evaluate_entries') as buy:
            rows=engine.base.execute_cycle(self.state,self.ledger,radar,engine.CONTEXT['quotes'],self.prices,self.now,True)
        self.assertTrue(rows);self.assertEqual(rows[0]['reasonCode'],'HARD_STOP');buy.assert_not_called()
    def test_stale_price_and_outside_session_never_fake_protection_sale(self):
        fixtures.SelectionTests.refresh(self,9.4);self.now+=timedelta(minutes=10)
        with patch.object(engine.base,'evaluate_exits',side_effect=engine.evaluate_exits):
            self.assertEqual(engine.base.execute_cycle(self.state,self.ledger,{},engine.CONTEXT['quotes'],self.prices,self.now,True),[])
            self.now=self.now.replace(hour=12)
            self.assertEqual(engine.base.execute_cycle(self.state,self.ledger,{},engine.CONTEXT['quotes'],self.prices,self.now,True),[])
    def test_execution_quote_path_never_calls_slow_or_secondary_collectors(self):
        def read(path,default=None):
            if path==engine.base.STATE_PATH:return deepcopy(self.state)
            return default or {}
        with patch.object(engine.base,'read_json',side_effect=read),patch.object(engine,'ORIGINAL_QUOTES',return_value=engine.CONTEXT['quotes']),patch.object(engine.feeds,'enrich',side_effect=AssertionError('slow collection')),patch.object(engine.feeds,'refresh_secondary',side_effect=AssertionError('secondary collection')):
            result=engine.prepare_quotes(['000001'])
        self.assertIn('000001',result)
    def test_slow_producer_never_writes_ledger_or_portfolio(self):
        writes=[]
        with patch.object(collector.base,'read_json',side_effect=lambda p,d=None:deepcopy(self.state) if p==engine.base.STATE_PATH else (d or {})),patch.object(collector.base,'fetch_tencent_quotes',return_value={}),patch.object(collector.feeds,'enrich',return_value={}),patch.object(collector.feeds,'refresh_secondary',return_value={}),patch.object(collector.base,'write_json',side_effect=lambda p,d:writes.append(p)):
            collector.collect()
        self.assertTrue(writes)
        self.assertFalse(any('astock_ai_portfolio' in str(p) for p in writes))
    def test_evidence_arrival_wakes_only_independent_writer(self):
        self.assertEqual(arrival.targets('radar-evidence',self.now),('run-ai-shadow-auto.yml',))
        self.assertNotIn('astock_ai_portfolio',arrival.CHANNELS['radar-evidence'])
    def test_workflows_have_separate_queues_and_no_producer_ledger_writes(self):
        root=Path(__file__).resolve().parents[1]/'.github/workflows'
        r=(root/'run-intraday-radar.yml').read_text();t=(root/'run-ai-shadow-auto.yml').read_text()
        self.assertIn('group: astock-radar-evidence-producer',r)
        self.assertIn('group: astock-radar-ai-shadow-production',t)
        self.assertNotIn('run: python tools/run_ai_dynamic_portfolio_v2_2.py',r)
        self.assertNotIn('run: python tools/enrich_ai_shadow_benchmarks.py',r)
    def test_overlay_parallel_fallback_keeps_actual_coverage(self):
        calls=[]
        def post(path,body):
            calls.append((path,body))
            return 503,'',{}
        with patch.object(overlay,'post',side_effect=post):out=overlay.fetch_stock_overlay(['000001','000002','920001'])
        self.assertFalse(out['000001']['quoteOk']);self.assertEqual(out['920001']['unsupportedMarket'],'BSE')
        self.assertEqual(len(calls),4)

if __name__=='__main__':unittest.main()
