import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
from urllib.error import HTTPError
from matcher.normalize import normalize
from matcher.scoring import score_pair,duplicate_pairs
from matcher.pipeline import run,load_events,DEFAULT_DATA
from matcher.evaluate import evaluate
from matcher.api import make_handler


class MatchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result=run()
        cls.crm=json.loads((DEFAULT_DATA/'crm_events.json').read_text())
        cls.cal=json.loads((DEFAULT_DATA/'calendar_events.json').read_text())
        cls.labels=json.loads((DEFAULT_DATA/'evaluation_labels.json').read_text())

    def test_labeled_regression(self):
        report=evaluate(self.result,self.labels)
        self.assertEqual(report['cross_source']['tp'],8)
        self.assertEqual(report['cross_source']['tn'],5)
        self.assertEqual(report['cross_source']['fp'],0)
        self.assertEqual(report['cross_source']['fn'],0)

    def test_unlabeled_pairs_excluded(self):
        report=evaluate(self.result,{'cross_source_pairs':self.labels['cross_source_pairs'][:1]})
        self.assertEqual(report['cross_source']['labeled_pairs'],1)
        self.assertEqual(report['cross_source']['tn'],0)

    def test_date_repair(self):
        e=normalize(self.crm[7],'crm')
        self.assertEqual(str(e.day),'2025-03-15')
        self.assertTrue(e.warnings)

    def test_timezone_uses_dst(self):
        a=normalize(self.crm[3],'crm')
        b=normalize(self.cal[3],'calendar')
        self.assertEqual(abs((a.instant-b.instant).total_seconds())/60,60)

    def test_bad_date_does_not_match(self):
        r={**self.crm[0],'meeting_date':'impossible'}
        p=score_pair(normalize(r,'crm'),normalize(self.cal[0],'calendar'))
        self.assertFalse(p['match'])
        self.assertTrue(p['warnings'])

    def test_missing_time_can_match(self):
        p=score_pair(normalize(self.crm[6],'crm'),normalize(self.cal[7],'calendar'))
        self.assertTrue(p['match'])
        self.assertIsNone(p['features']['time'])

    def test_modality_conflict_not_veto(self):
        p=score_pair(normalize(self.crm[1],'crm'),normalize(self.cal[1],'calendar'))
        self.assertTrue(p['match'])
        self.assertTrue(any('modality' in s for s in p['warnings']))

    def test_recurrences_not_duplicates(self):
        events=[normalize(self.cal[i],'calendar') for i in (2,17)]
        self.assertEqual(duplicate_pairs(events),[])

    def test_duplicate_candidate(self):
        pairs=self.result['duplicate_candidates']
        self.assertEqual([(p['record_a'],p['record_b']) for p in pairs],[('CAL-A5','CAL-A6')])

    def test_email_repair_and_placeholder(self):
        e=normalize(self.cal[15],'calendar')
        self.assertIn('raj.patel@atlasvc.com',e.emails)
        self.assertNotIn('external-guests',normalize(self.cal[19],'calendar').emails)

    def test_duplicate_id_quarantined(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'data.json'
            path.write_text(json.dumps([self.crm[0],self.crm[0],{}]))
            events,bad=load_events(path,'crm','America/New_York')
            self.assertEqual(len(events),1)
            self.assertEqual(len(bad),2)

    def test_no_mutation(self):
        record=copy.deepcopy(self.cal[15])
        original=copy.deepcopy(record)
        normalize(record,'calendar')
        self.assertEqual(record,original)

    def test_labels_not_required_for_inference(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ('crm_events.json','calendar_events.json'):
                (Path(d)/name).write_bytes((DEFAULT_DATA/name).read_bytes())
            self.assertEqual(run(d)['predictions'],self.result['predictions'])

    def test_api_real_http(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.result))
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(base+'/health',timeout=5) as response:
                self.assertEqual(json.load(response)['status'],'ok')
            with urlopen(base+'/predict?crm_id=CRM-1001&calendar_id=CAL-A1',timeout=5) as response:
                self.assertTrue(json.load(response)['match'])
            with urlopen(base+'/matches?crm_id=CRM-1005',timeout=5) as response:
                self.assertEqual(len(json.load(response)),2)
            with urlopen(base+'/duplicates',timeout=5) as response:
                self.assertEqual(len(json.load(response)),1)
            for route,status in [('/predict',400),('/predict?crm_id=bad&calendar_id=bad',404),('/missing',404)]:
                with self.assertRaises(HTTPError) as error:
                    urlopen(base+route,timeout=5)
                self.assertEqual(error.exception.code,status)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

if __name__=='__main__':
    unittest.main()
