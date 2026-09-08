import sys, unittest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch
from urllib.parse import urlparse, parse_qs
sys.path.insert(0,str(Path(__file__).resolve().parent))
import update_market_gateway as gateway
import selection_data_v45 as feeds
from selection_rules_v45 import CN

class RecoveryTests(unittest.TestCase):
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
