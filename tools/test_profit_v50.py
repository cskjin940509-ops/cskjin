import sys, unittest, json
from unittest.mock import patch
from pathlib import Path
from datetime import datetime, timedelta
sys.path.insert(0, str(Path(__file__).resolve().parent))
import selection_rules_v45 as rules
import selection_engine_v45 as engine
import test_rotation_v49 as fixtures

class ProfitRulesTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.fromisoformat('2026-09-09T10:10:00+08:00')
        self.pos = dict(qty=900, riskBasis=100., avgCost=100.)
        self.tech = dict(ready=True, high20=110., atr14=4.)
        rules.profit_signal(self.pos,110.,self.tech,[],self.now-timedelta(minutes=7))
        self.samples = [dict(at=(self.now-timedelta(minutes=m)).isoformat(),price=p)
                        for m,p in [(6,110.5),(3,110.4),(0,110.)]]
    def signal(self):return rules.profit_signal(self.pos,110.,self.tech,self.samples,self.now)
    def test_stall_inside_frozen_target_trims_third(self):
        self.assertEqual(self.signal()['qty'],300)
        self.tech['high20']=150.
        self.assertEqual(self.signal()['targetPrice'],110.)
    def test_strong_uptrend_not_sold(self):
        self.samples[0]['price']=109.;self.samples[1]['price']=109.5
        self.assertIsNone(self.signal())
    def test_duplicate_stale_or_pre_activation_samples_do_not_sell(self):
        self.samples[1]['at']=self.samples[0]['at'];self.assertIsNone(self.signal())
        self.setUp();self.pos['profitPlan50']['activatedAt']=self.now.isoformat();self.assertIsNone(self.signal())
        self.setUp();self.now+=timedelta(minutes=20);self.assertIsNone(self.signal())
    def test_missing_history_no_target_and_no_sale(self):
        self.tech['ready']=False;self.assertIsNone(self.signal())
    def test_stage_persists_restart_and_only_one_per_day(self):
        self.pos['profitPlan50'].update(queuedStages=[1],lastQueuedDay=self.now.date().isoformat())
        self.pos=json.loads(json.dumps(self.pos));self.assertIsNone(self.signal())
        self.pos['profitPlan50']['lastQueuedDay']='2026-09-08'
        self.samples=[dict(x,price=x['price']+6) for x in self.samples]
        result=rules.profit_signal(self.pos,116.,self.tech,self.samples,self.now)
        self.assertEqual((result['stage'],result['qty']),(2,400))
        self.pos['profitPlan50']['queuedStages'].append(2)
        self.assertIsNone(rules.profit_signal(self.pos,116.,self.tech,self.samples,self.now))
    def test_progressive_trail_never_loosens(self):
        pos=dict(riskBasis=100,avgCost=100)
        a=rules.stop_lines(pos,116,dict(ready=True,atr14=10))
        self.assertAlmostEqual(a['trailingStopPrice'],116*.95)
        pos.update(a)
        b=rules.stop_lines(pos,126,dict(ready=True,atr14=10))
        self.assertAlmostEqual(b['trailingStopPrice'],126*.97)
        pos.update(b)
        c=rules.stop_lines(pos,115,dict(ready=True,atr14=20))
        self.assertGreaterEqual(c['trailingStopPrice'],b['trailingStopPrice'])

class ProfitExecutionTests(unittest.TestCase):
    def setUp(self):fixtures.RotationTests.setUp(self)
    def queue(self):
        self.pos=self.state['positions']['000001']
        engine.queue_exit(self.state,self.pos,60000,'PROFIT_TAKE','主动止盈',{'stage':1})
    def test_protection_sale_outside_normal_window_cancels_t(self):
        self.now=self.now.replace(hour=9,minute=45)
        engine.CONTEXT['quotes']['000001']['quoteTime']=self.now.isoformat()
        obj=engine.metadata(self.state)
        obj['tCycles']=[dict(code='000001',status='OPEN')]
        self.queue()
        rows=engine.execute_pending(self.state,self.ledger,self.prices)
        self.assertEqual(rows[0]['reasonCode'],'PROFIT_TAKE')
        self.assertEqual(obj['tCycles'][0]['status'],'RISK_CANCELLED')
        self.assertGreater(self.state['cash'],0)
    def test_t1_waits_and_hard_stop_supersedes_trim(self):
        self.queue();self.pos['dailyBuyQty']={'2026-09-09':200000}
        self.assertEqual(engine.execute_pending(self.state,self.ledger,self.prices),[])
        pending=engine.metadata(self.state)['pendingExits']['000001']
        self.assertEqual(pending['state'],'WAIT_T_PLUS_ONE')
        engine.queue_exit(self.state,self.pos,200000,'HARD_STOP','止损')
        self.assertEqual(engine.metadata(self.state)['pendingExits']['000001']['reasonCode'],'HARD_STOP')
    def test_engine_integrates_signal_and_does_not_repeat_after_fill(self):
        pos=self.state['positions']['000001'];pos['riskBasis']=8.
        tech={'ready':True,'high20':10.,'atr14':.3}
        start=self.now-timedelta(minutes=7)
        rules.profit_signal(pos,10.,tech,[],start)
        samples=[dict(at=(self.now-timedelta(minutes=m)).isoformat(),price=p)
                 for m,p in [(6,10.05),(3,10.04),(0,10.)]]
        with patch.object(engine,'technical',return_value=tech), patch.object(engine,'sample',return_value=samples), patch.object(engine,'start_no_t_control'):
            rows=engine.evaluate_exits(self.state,self.ledger,self.radar['stocks'],engine.CONTEXT['quotes'],self.prices)
            self.assertTrue(any(x.get('reasonCode')=='PROFIT_TAKE' for x in rows))
            qty=pos['qty']
            engine.evaluate_exits(self.state,self.ledger,self.radar['stocks'],engine.CONTEXT['quotes'],self.prices)
            self.assertEqual(pos['qty'],qty)
    def test_partial_fill_survives_restart_without_repeat_sale(self):
        self.queue();engine.base.EXECUTION_MARKET['000001']['amount']=1e6
        rows=engine.execute_pending(self.state,self.ledger,self.prices)
        self.assertTrue(rows);self.assertLess(rows[0]['qty'],60000)
        remaining=60000-rows[0]['qty']
        self.state=json.loads(json.dumps(self.state))
        self.assertEqual(engine.metadata(self.state)['pendingExits']['000001']['remainingQty'],remaining)

if __name__=='__main__':unittest.main()
