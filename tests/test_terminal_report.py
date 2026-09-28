import json
import unittest
from lab.terminal_report import summarize, markdown


class TerminalReportTests(unittest.TestCase):
    def fixture(self):
        lock={'tasks':[{'id':'private-task-a'},{'id':'private-task-b'}],'k':5,'dataset_commit':'pinned','version':'fixture'}
        def rows(passes):
            return [{'task_id':t['id'],'repetition':r,'dataset_commit':'pinned','verifier':'harbor-official',
                'evaluation_fingerprint':'fixed','accounting_complete':True,'reward':int(r<passes),
                'tokens':100,'cost_usd':.01,'evaluation_label':'Test fixture only'} for t in lock['tasks'] for r in range(5)]
        return dict(lock=lock,variants=[{'name':'standard','iteration':0,'rows':rows(2)},
            {'name':'improvement-one','iteration':1,'rows':rows(3)}],champion='improvement-one')

    def test_report_distinguishes_percentage_points_and_relative_gain(self):
        report=summarize(**self.fixture());effect=report['rows'][1]['vs_original_plain_dsh']
        self.assertAlmostEqual(effect['change_percentage_points'],20)
        self.assertAlmostEqual(effect['relative_change_pct'],50)
        self.assertIn('+20.00 pp',markdown(report));self.assertIn('+50.00%',markdown(report))
        self.assertNotIn('private-task',json.dumps(report))
        self.assertEqual(report['rows'][1]['final_champion_vs_this_variant']['relative_change_pct'],0)

    def test_cannot_omit_attempt_or_partial_final_champion(self):
        args=self.fixture();args['variants'][1]['iteration']=2
        with self.assertRaises(ValueError):summarize(**args)
        args=self.fixture();args['variants'][1]['rows'].pop()
        with self.assertRaises(ValueError):summarize(**args)
