import copy, sys, unittest
from datetime import datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from portfolio_returns_v48 import build_report
from execution_status_v48 import explain
class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.state={'fundAccounting':{'inceptionCapital':1000000},'capitalEvents':[{'timestamp':'2026-09-03T23:23:35+08:00','toCapital':20000000,'cashContribution':19000000}], 'cash':19998999.,'positions':{'600001':{'qty':100}}}
        self.ledger=[{'decisionId':'1','timestamp':'2026-09-03T10:00:00+08:00','code':'600001','qty':100,'side':'BUY','amount':1000.,'fee':1.}]
        self.now=datetime.fromisoformat('2026-09-07T16:00:00+08:00')
        self.closes={'600001':{'2026-09-03':10.,'2026-09-04':11.,'2026-09-07':12.}}
        self.days=['2026-09-03','2026-09-04','2026-09-07']
    def report(self): return build_report(self.state,self.ledger,self.closes,self.days,self.now)
    def test_deposit_is_not_profit_and_daily_denominator(self):
        original=copy.deepcopy((self.state,self.ledger)); r=self.report()['rows']
        self.assertEqual(r[0]['closeAssets'],19999999.)
        self.assertIsNone(r[0]['dailyReturnPct'])
        self.assertEqual(r[1]['dailyPnl'],100.)
        self.assertAlmostEqual(r[1]['dailyReturnPct'],100/19999999*100)
        self.assertEqual(r[2]['previousCloseAssets'],20000099.)
        self.assertEqual(original,(self.state,self.ledger))
    def test_missing_close_does_not_bridge_gap(self):
        del self.closes['600001']['2026-09-04']; r=self.report()['rows']
        self.assertIsNone(r[1]['dailyReturnPct']); self.assertIsNone(r[2]['dailyReturnPct']); self.assertIsNone(r[2]['cumulativeReturnPct'])
    def test_replay_mismatch_fails(self):
        self.state['positions']['600001']['qty']=200
        with self.assertRaises(ValueError): self.report()
    def test_intraday_not_frozen_as_close(self):
        self.now=self.now.replace(hour=14); self.assertEqual(len(self.report()['rows']),2)
    def test_blocking_reason_not_threshold(self):
        r=explain({'selection45':{'market':{'state':'UNKNOWN','reasonZh':'全市场广度缺失'},'portfolioRisk':{'dailyRiskDataReady':False,'allowNew':False}}})
        self.assertEqual(r['reasonCode'],'BLOCKED_EVIDENCE_OR_RISK'); self.assertIn('广度缺失',r['reasonZh']); self.assertNotIn('阈值',r['reasonZh'])
    def test_pending_exit_is_not_no_signal(self):
        r=explain({'selection45':{'pendingExits':[{'code':'600001','state':'WAIT_T_PLUS_ONE'}]}})
        self.assertEqual(r['reasonCode'],'PENDING_EXECUTION'); self.assertIn('T+1',r['reasonZh'])
if __name__=='__main__': unittest.main()
