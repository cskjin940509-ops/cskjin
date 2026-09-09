import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from datetime import date, timedelta
from original_framework import sentiment_candidate, alignment_report

class SentimentTests(unittest.TestCase):
    def rows(self, n=485):
        start = date(2020, 1, 1)
        return [dict(dataDate=(start+timedelta(days=i)).isoformat(),
                     availableAt=(start+timedelta(days=i+1)).isoformat()+'T08:00:00+08:00',
                     source='test-fixture', universe='fixed-test-universe', verified=True,
                     up=2000+i, down=2000-i, financingBalance=10000+i*i,
                     previousFinancingBalance=10000+(i-1)*(i-1)) for i in range(n)]
    def score(self, rows, kind='profit'):
        return sentiment_candidate(rows, kind, '2026-09-09T12:00:00+08:00', 'fixed-test-universe')
    def test_no_padding_or_duplicate_days(self):
        rows=self.rows(484)
        self.assertIsNone(self.score(rows+[rows[-1]])['score'])
    def test_rank_and_research_boundary(self):
        self.assertEqual(self.score(self.rows())['score'],100)
        self.assertFalse(self.score(self.rows())['productionEligible'])
        self.assertEqual(self.score(self.rows(),'margin')['score'],100)
    def test_future_wrong_universe_and_conflicts(self):
        for key,val in [('availableAt','2030-01-01T00:00:00+08:00'),('universe','other'),('verified',False)]:
            rows=self.rows();rows[-1][key]=val
            self.assertIsNone(self.score(rows)['score'])
        rows=self.rows();rows.append(dict(rows[-1],up=9999))
        self.assertEqual(self.score(rows)['status'],'CONFLICTING_OBSERVATIONS')
    def test_original_hierarchy_not_fourth_top_layer(self):
        report=alignment_report()
        self.assertEqual([x['id'] for x in report['topLevel']],['market','sector','stock'])
        self.assertFalse(report['complete'])
if __name__=='__main__': unittest.main()
