import sys, unittest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch
from urllib.parse import urlparse, parse_qs
sys.path.insert(0,str(Path(__file__).resolve().parent))
import update_market_gateway as gateway
import selection_data_v45 as feeds
import run_ai_shadow_portfolio as portfolio
import tushare_stock_api as stock_api
import ensure_daily_close_snapshot as close_snapshot
import ensure_market_snapshot_core_indices as core_indices
from selection_rules_v45 import CN, confirmation_samples

class RecoveryTests(unittest.TestCase):
    def test_arrival_bursts_do_not_destroy_spaced_observations(self):
        now=datetime(2026,9,8,13,40,tzinfo=CN)
        rows=[{'at':(now-timedelta(seconds=seconds)).isoformat(),'price':10} for seconds in (420,390,360,210,180,150,60,30,0)]
        picked=confirmation_samples(rows)
        self.assertEqual([x['at'] for x in picked], [rows[2]['at'],rows[4]['at'],rows[-1]['at']])
        self.assertEqual(len(rows),9)
    def test_sector_route_falls_back_on_http_failure(self):
        import io
        from urllib.error import HTTPError
        response=io.BytesIO(b'{"data":{"total":1}}')
        with patch.object(feeds,'urlopen',side_effect=[HTTPError('https://push2.eastmoney.com/',502,'bad gateway',{},None),response]) as fetch:
            result=feeds.get_json('https://push2.eastmoney.com/api/qt/clist/get?pn=1')
        self.assertEqual(result['data']['total'],1)
        self.assertIn('push2delay.eastmoney.com',fetch.call_args.args[0].full_url)
    def test_board_uses_board_market_id(self):
        rows=['2026-09-07,10,10,11,9,100,1000']*21
        with patch.object(feeds,'get_json',return_value={'data':{'klines':rows}}) as fetch:
            feeds.daily_bars('BK0478')
        self.assertEqual(parse_qs(urlparse(fetch.call_args.args[0]).query)['secid'],['90.BK0478'])
    def test_capped_pages_collected_completely(self):
        def response(url):
            page=int(parse_qs(urlparse(url).query)['pn'][0]); start=(page-1)*100
            return {'data':{'total':2301,'diff':[{'f12':str(i),'f13':0,'f3':1,'f6':10} for i in range(start,min(start+100,2301))]}}
        with patch.object(gateway,'get_json',side_effect=response):
            result=gateway.all_a_breadth()
        self.assertEqual(result['sampleCount'],2301)
        self.assertEqual(result['totalAmount'],23010)
    def test_board_failover_uses_same_day_tushare_ths(self):
        sample=[{'boardCode':'885001.TI','name':'人工智能','changePct':2.5,'source':'Tushare/THS'}]
        with patch.object(gateway,'boards',side_effect=TimeoutError()), patch.object(stock_api,'ths_board_flows',return_value=sample) as backup:
            result=gateway.boards_with_failover('concept','20261009')
        self.assertEqual(result,sample)
        backup.assert_called_once_with('concept','20261009')
    def test_partial_eastmoney_board_triggers_secondary_provider(self):
        with patch.object(gateway,'eastmoney_clist',return_value=[{'f12':'BK1','f14':'partial'}]), \
             patch.object(stock_api,'ths_board_flows',return_value=[{'name':f'x{i}'} for i in range(100)]) as backup:
            result=gateway.boards_with_failover('concept','20261009')
        self.assertEqual(len(result),100)
        backup.assert_called_once_with('concept','20261009')
    def test_market_breadth_failover_uses_requested_date(self):
        sample={'sampleCount':4500,'source':'Tushare daily'}
        with patch.object(gateway,'all_a_breadth',side_effect=TimeoutError()), patch.object(stock_api,'daily_market_breadth',return_value=sample) as backup:
            self.assertEqual(gateway.breadth_with_failover('20261009'),sample)
        backup.assert_called_once_with('20261009')
    def test_stock_api_ths_board_normalization_and_date_guard(self):
        rows=[{'trade_date':'20261009','ts_code':f'885{i:03d}.TI','name':f'概念{i}',
               'pct_change':1.5,'net_amount':2.0,'company_num':20} for i in range(100)]
        frame=type('Frame',(),{'empty':False,'to_dict':lambda self,orient:rows})()
        pro=type('Pro',(),{'moneyflow_cnt_ths':lambda self,**kwargs:frame})()
        with patch.object(stock_api,'pro_api',return_value=pro):
            out=stock_api.ths_board_flows('concept','20261009')
        self.assertEqual(len(out),100)
        self.assertEqual(out[0]['boardCode'],'885000.TI')
        self.assertEqual(out[0]['mainNetFlow'],200_000_000)
        self.assertIsNone(out[0]['mainFlowPct'])
    def test_stock_api_breadth_rejects_stale_or_partial_data(self):
        rows=[{'trade_date':'20261008','ts_code':f'{i:06d}.SH','pct_chg':1,'amount':10} for i in range(4500)]
        frame=type('Frame',(),{'empty':False,'to_dict':lambda self,orient:rows})()
        pro=type('Pro',(),{'daily':lambda self,**kwargs:frame})()
        with patch.object(stock_api,'pro_api',return_value=pro):
            with self.assertRaises(RuntimeError):
                stock_api.daily_market_breadth('20261009')
    def test_stock_api_breadth_accepts_full_same_day_cross_section(self):
        rows=[{'trade_date':'20261009','ts_code':f'{i:06d}.SH','pct_chg':1 if i%2 else -1,'amount':10} for i in range(4500)]
        frame=type('Frame',(),{'empty':False,'to_dict':lambda self,orient:rows})()
        pro=type('Pro',(),{'daily':lambda self,**kwargs:frame})()
        with patch.object(stock_api,'pro_api',return_value=pro):
            out=stock_api.daily_market_breadth('20261009')
        self.assertEqual(out['sampleCount'],4500)
        self.assertEqual(out['up'],2250)
        self.assertEqual(out['totalAmount'],45_000_000)
    def test_repeated_first_page_rejected(self):
        response={'data':{'total':2301,'diff':[{'f12':str(i),'f13':0,'f3':1} for i in range(100)]}}
        with patch.object(gateway,'get_json',return_value=response):
            with self.assertRaises(RuntimeError): gateway.all_a_breadth()
    def test_failed_and_amountless_history_retries(self):
        now=datetime(2026,9,8,13,30,tzinfo=CN)
        bars=[{'date':(now-timedelta(days=i)).date().isoformat(),'amount':None} for i in range(1,30)]
        self.assertTrue(feeds.history_due({'collectedDate':'2026-09-08','bars':bars},now))
        self.assertTrue(feeds.history_due({'collectedDate':'2026-09-08','bars':[]},now))
        self.assertFalse(feeds.history_due({'lastAttemptAt':now.isoformat()},now))
        for b in bars:b['amount']=1000
        self.assertFalse(feeds.history_due({'collectedDate':'2026-09-08','bars':bars},now))
    def test_tencent_fallback_never_invents_amount(self):
        rows=[['2026-09-07','10','10','11','9'],['2026-09-04','10','10','11','9']]
        def response(url):
            if 'eastmoney' in url: raise TimeoutError()
            return {'data':{'sz000001':{'qfqday':rows}}}
        with patch.dict('os.environ',{},clear=True), patch.object(feeds,'get_json',side_effect=response):
            result=feeds.daily_bars('000001')
        self.assertIsNone(result[0]['amount'])
        self.assertIsNone(result[1]['amount'])
    def test_secondary_stale_price_never_marked_fresh(self):
        radar={'stocks':{'000001':{}}}
        now=datetime.now(CN)
        quote={'000001':{'quoteOk':True,'price':10,'quoteTime':(now-timedelta(hours=1)).isoformat()}}
        with patch.dict('os.environ',{'STOCK_API_TOKEN':'test'}), patch('tushare_stock_api.realtime_quotes',return_value=quote):
            result=feeds.refresh_secondary(radar,['000001'],now)
        self.assertEqual(result['fresh'],0)
        self.assertFalse(radar['stocks']['000001']['stockApi']['quoteOk'])
    def test_quote_merge_prefers_freshest_approved_source(self):
        tushare={'000001':{'price':10.0,'quoteTime':'20260922093000','source':'Tushare compatible stock_api realtime_quote'}}
        tencent={'000001':{'price':10.2,'high':10.3,'quoteTime':'20260922094500','source':'腾讯实时行情'}}
        out=portfolio._merge_quotes([tushare,tencent],['000001'])['000001']
        self.assertEqual(out['price'],10.2)
        self.assertEqual(out['selectedProvider'],'腾讯实时行情')
        self.assertEqual(out['high'],10.3)
        self.assertEqual(len(out['availableProviders']),2)
    def test_quote_merge_accepts_one_source_without_dual_gate(self):
        eastmoney={'600000':{'price':9.8,'quoteTime':'20260922100000','source':'东方财富实时行情'}}
        out=portfolio._merge_quotes([eastmoney],['600000'])['600000']
        self.assertEqual(out['price'],9.8)
        self.assertEqual(out['selectedProvider'],'东方财富实时行情')
    def test_close_freeze_requires_same_day_index_quotes(self):
        day='2026-10-09'
        indices={code:{'quoteTime':'150000','quoteDate':'20261008'} for code in close_snapshot.CORE}
        payload={'verifiedToday':True,'marketSnapshot':{'sourceDate':day,'indices':indices},
                 'boardHeatmap':{'industry':[{}]*30,'concept':[{}]*100}}
        ok,detail=close_snapshot.readiness(payload,day)
        self.assertFalse(ok)
        self.assertEqual(detail['closeCoreCount'],0)
    def test_core_index_patch_preserves_provider_date(self):
        payload={'marketSnapshot':{'sourceDate':'2026-10-09','indices':{}}}
        quotes={'sh000001':{'name':'上证指数','close':3800,'quoteTime':'150001','quoteDate':'20261009'}}
        self.assertTrue(core_indices.patch_payload(payload,quotes,'2026-10-09'))
        self.assertEqual(payload['marketSnapshot']['indices']['sh000001']['quoteDate'],'20261009')
if __name__=='__main__':unittest.main()
