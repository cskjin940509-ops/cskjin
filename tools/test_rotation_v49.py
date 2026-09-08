import sys, unittest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch
from copy import deepcopy
sys.path.insert(0,str(Path(__file__).resolve().parent))
import selection_engine_v45 as engine
import selection_rotation_v49 as rotation

class RotationTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime.fromisoformat('2026-09-09T10:15:00+08:00')
        self.addCleanup(patch.stopall)
        patch.object(engine.base,'now_cn',side_effect=lambda:self.now).start()
        patch.object(engine,'risk_control',return_value={'allowNew':True,'forceReduction':False,'cap':1.}).start()
        engine.CONTROL_MODE=None;engine.NO_T_CONTROL=False
        self.state=engine.base.new_state(); self.state['cash']=0.; self.state['positions']={}
        self.prices={}
        for i in range(10):
            c=f'{i+1:06d}'; self.prices[c]=10.
            self.state['positions'][c]=dict(code=c,name=c,sector='S'+c,qty=200000,avgCost=10.,costAmount=2000000.,
                entryDate='2026-09-01',dailyBuyQty={},lastPrice=10.,completeObservedDays=4,correlationGroup='G'+c,
                invalidationZh='test',expectedHorizonZh='test',entryPrice=10.)
        self.buyer='000099';self.prices[self.buyer]=10.
        self.ledger=[];self.radar={'stocks':{},'mainlines':[]}; quotes={};tech={};ranks={}
        for c in ('000001',self.buyer):
            sector='S'+c
            self.radar['stocks'][c]={'code':c,'name':c,'sector':sector,'mainFlowPct':2.,'changePct':0.,
                'yunai':{'quoteOk':True,'price':10.,'quoteTime':self.now.isoformat()}}
            self.radar['mainlines'].append({'name':sector,'stage':'CONFIRMING','breadthPct':70,'changePct':0.,'mainFlowPct':2.,'return5Pct':1.})
            quotes[c]={'price':10.,'prevClose':10.,'quoteTime':self.now.isoformat(),'amount':1e9}
            tech[c]={'ready':True,'adv20':1e9,'atr14':.3,'high20':12. if c==self.buyer else 10.5}
            ranks[sector]={'complete':True,'ranks':{c:.1},'rows':{}}
        engine.CONTEXT.clear();engine.CONTEXT.update(radar=self.radar,quotes=quotes,market={'state':'STRONG','cap':1.,'allowNew':True})
        self.state['selectionData45']={'technical':tech,'sectorRanks':ranks}
        engine.base.EXECUTION_MARKET=deepcopy(quotes)
        obj=engine.metadata(self.state);obj['confirmations']={self.buyer:{'count':3}}
        obj['rotation49']={'plans':[], 'proposal':{'pair':'000001>'+self.buyer,'count':3,'at':self.now.isoformat()}}
        self.targets=[dict(code=c,name=c,sector='S'+c,referencePrice=10.,score=85 if c==self.buyer else 65,
            technical=tech[c],rejections=[],targetWeight=.04,targetWeightPct=4.,priceSource='test',reasonZh='test',correlationGroup='G'+c)
            for c in ('000001',self.buyer)]
    def run_rotation(self):
        return rotation.run(engine,self.state,self.ledger,self.targets,self.radar,self.prices)
    def plan(self):return self.state['selection45']['rotation49'].get('active')
    def test_full_cash_account_sells_before_buy_and_never_borrows(self):
        rows=self.run_rotation()
        self.assertEqual([x['side'] for x in rows],['SELL','BUY'])
        self.assertGreaterEqual(self.state['cash'],0)
        self.assertLessEqual(rows[1]['amount']+rows[1]['fee'],rows[0]['amount']-rows[0]['fee'])
        self.assertEqual(rows[0]['rotationId'],rows[1]['rotationId'])
        self.assertEqual(self.state['positions']['000001']['qty'],200000-rows[0]['qty'])
    def test_same_tick_does_not_confirm_relative_advantage(self):
        self.state['selection45']['rotation49'].pop('proposal')
        for _ in range(4):self.assertEqual(self.run_rotation(),[])
        self.assertEqual(self.state['selection45']['rotation49']['proposal']['count'],1)
        self.assertEqual(self.ledger,[])
    def test_weaker_advantage_never_forces_trade(self):
        self.targets[-1]['score']=70
        self.assertEqual(self.run_rotation(),[]);self.assertEqual(self.ledger,[])
    def test_missing_donor_evidence_is_not_weakness(self):
        self.state['selectionData45']['sectorRanks']['S000001']['complete']=False
        self.assertEqual(self.run_rotation(),[])
    def test_t1_donor_retains_waiting_plan_without_buy(self):
        self.state['positions']['000001']['dailyBuyQty']={'2026-09-09':200000}
        self.assertEqual(self.run_rotation(),[])
        self.assertEqual(self.plan()['status'],'WAIT_T_PLUS_ONE')
    def test_blocked_new_stock_does_not_sell_old(self):
        engine.base.EXECUTION_MARKET[self.buyer]['amount']=0
        self.assertEqual(self.run_rotation(),[])
        self.assertEqual(self.plan()['status'],'WAIT_BUY_CAPACITY')
    def test_blocked_sale_does_not_create_cash(self):
        engine.base.EXECUTION_MARKET['000001']['amount']=0
        self.assertEqual(self.run_rotation(),[])
        self.assertEqual(self.state['cash'],0)
        self.assertEqual(self.plan()['status'],'WAIT_SELL_CAPACITY')
    def test_partial_sale_only_funds_partial_buy(self):
        engine.base.EXECUTION_MARKET['000001']['amount']=1e6
        rows=self.run_rotation()
        self.assertEqual([x['side'] for x in rows],['SELL','BUY'])
        self.assertLess(rows[0]['qty'],self.plan()['requestedSellQty'])
        self.assertLessEqual(rows[1]['amount']+rows[1]['fee'],rows[0]['amount']-rows[0]['fee'])
        self.assertEqual(self.plan()['status'],'PARTIAL_WAIT')
    def test_invalidated_target_stops_remaining_sale(self):
        engine.base.EXECUTION_MARKET['000001']['amount']=1e6
        self.run_rotation();old=deepcopy(self.ledger)
        self.targets[-1]['rejections']=['涨过买入区间']
        self.assertEqual(self.run_rotation(),[])
        self.assertEqual(self.plan()['status'],'CANCELLED');self.assertEqual(self.ledger,old)
    def test_expired_plan_does_not_execute_next_day(self):
        self.state['positions']['000001']['dailyBuyQty']={'2026-09-09':200000};self.run_rotation()
        self.now+=timedelta(days=1)
        self.assertEqual(self.run_rotation(),[]);self.assertEqual(self.plan()['status'],'EXPIRED')
    def test_expiry_visible_even_without_trading_cycle(self):
        self.state['positions']['000001']['dailyBuyQty']={'2026-09-09':200000};self.run_rotation()
        rotation.expire_snapshot(self.state['selection45'],self.now+timedelta(hours=6))
        self.assertEqual(self.plan()['status'],'EXPIRED');self.assertEqual(self.ledger,[])
    def test_risk_exit_wins_over_rotation(self):
        self.state['selection45']['pendingExits']={'000001':{'state':'WAIT_T_PLUS_ONE'}}
        self.assertEqual(self.run_rotation(),[])
    def test_restart_does_not_reset_sold_quantity(self):
        import json
        engine.base.EXECUTION_MARKET['000001']['amount']=1e6
        self.run_rotation();sold=self.plan()['soldQty'];self.state=json.loads(json.dumps(self.state))
        self.targets[-1]['rejections']=['信号失效'];self.run_rotation()
        self.assertEqual(self.plan()['soldQty'],sold)
        self.assertEqual(self.state['selection45']['rotation49']['plans'][0]['status'],'CANCELLED')

if __name__=='__main__':unittest.main()
