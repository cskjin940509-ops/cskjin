import sys, unittest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch
from urllib.parse import urlparse, parse_qs
sys.path.insert(0,str(Path(__file__).resolve().parent))
import update_market_gateway as gateway
import selection_data_v45 as feeds
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
    def test_fallback_amount_requires_same_date_and_price_basis(self):
        rows=[['2026-09-07','10','10','11','9'],['2026-09-04','10','10','11','9']]
        def response(url):
            if 'eastmoney' in url: raise TimeoutError()
            return {'data':{'sz000001':{'qfqday':rows}}}
        with patch.dict('os.environ',{'YUNAI_TOKEN':'test'}), patch.object(feeds,'get_json',side_effect=response), patch('yunai_tail_overlay.fetch_daily_kline',return_value=[{'date':'2026-09-07','close':10,'amount':1500},{'date':'2026-09-04','close':20,'amount':2000}]):
            result=feeds.daily_bars('000001')
        self.assertEqual(result[0]['amount'],1500)
        self.assertIsNone(result[1]['amount'])
    def test_secondary_stale_price_never_marked_fresh(self):
        radar={'stocks':{'000001':{'yunai':{'quoteOk':True,'price':10}}}}
        now=datetime.now(CN)
        with patch.dict('os.environ',{'YUNAI_TOKEN':'test'}), patch('yunai_tail_overlay.post',return_value=(200,'',{'data':{'000001':{'lastPrice':10,'timestamp':int((now-timedelta(hours=1)).timestamp()*1000)}}})):
            result=feeds.refresh_secondary(radar,['000001'],now)
        self.assertEqual(result['fresh'],0)
        self.assertFalse(radar['stocks']['000001']['yunai']['quoteOk'])
if __name__=='__main__':unittest.main()
