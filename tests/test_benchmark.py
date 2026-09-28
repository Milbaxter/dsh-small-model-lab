import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lab.statistics import paired_change
from lab.sweep import grade, write_files
from lab.metrics import failure_tag


class BenchmarkTests(unittest.TestCase):
    def test_paired_intervals_are_clustered_by_task_and_zero_baseline_is_explicit(self):
        base={(str(t),r):0 for t in range(8) for r in range(5)}
        candidate={k:1 for k in base}
        result=paired_change(base,candidate,draws=100)
        self.assertEqual(result['change_percentage_points'],100)
        self.assertEqual(result['paired_95ci_percentage_points'],[100,100])
        self.assertIsNone(result['relative_change_pct'])
        self.assertEqual(paired_change(candidate,candidate,draws=100)['change_percentage_points'],0)
        with self.assertRaises(ValueError):paired_change(base,{k:v for k,v in candidate.items() if k!=('0',0)})

    def test_hidden_expected_answers_never_enter_grading_container(self):
        task={'hidden':{'cases':[[[1,2],{'secret-expected-answer':3}]]}}
        class Result:
            returncode=0
            stdout=json.dumps({'results':[{'value':{'secret-expected-answer':3},'unchanged':True}]})
        with patch('lab.sweep.subprocess.run',return_value=Result()) as call:
            self.assertTrue(grade(task,Path('/tmp/workspace')))
            args=call.call_args_list[0]
            self.assertNotIn('secret-expected-answer',args.kwargs['input'])
            self.assertEqual(json.loads(args.kwargs['input']),{'kind':'code','inputs':[[1,2]]})
            self.assertIn('none',args.args[0])
            self.assertNotIn('LAB_VLLM_KEY',str(args))

    def test_grader_requires_exact_results_not_a_claimed_pass(self):
        class Result:
            returncode=0
            stdout='{"passed":true}'
        with patch('lab.sweep.subprocess.run',return_value=Result()):
            self.assertFalse(grade({'hidden':{'files':{'answer.json':42}}},Path('/tmp/workspace')))

    def test_task_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):write_files(Path(tmp),{'../escape':'x'})
            with self.assertRaises(ValueError):write_files(Path(tmp),{'/tmp/escape':'x'})

    def test_failure_tags_distinguish_budget_timeout_and_model_error(self):
        self.assertEqual(failure_tag('timeout',False,{},20),'TIMEOUT')
        self.assertEqual(failure_tag('completed',False,{'requests':20},20),'MAX_TURNS')
        self.assertEqual(failure_tag('completed',False,{'malformed_calls':1},20),'BAD_EDIT')
        self.assertIsNone(failure_tag('completed',True,{},20))


class IndependentGateTests(unittest.TestCase):
    def test_terminal_gate_requires_complete_official_paired_evidence(self):
        from lab.terminal_gate import compare
        lock={'tasks':[{'id':'a'},{'id':'b'}],'k':5,'dataset_commit':'pinned'}
        base=[{'task_id':t,'repetition':r,'dataset_commit':'pinned','verifier':'harbor-official',
               'accounting_complete':True,'reward':0} for t in ('a','b') for r in range(5)]
        cand=[{**r,'reward':1} for r in base]
        self.assertTrue(compare(lock,base,cand)['independent_gate_passed'])
        self.assertFalse(compare(lock,base,base)['independent_gate_passed'])
        with self.assertRaises(ValueError):compare(lock,base,cand[:-1])
        with self.assertRaises(ValueError):compare(lock,base,[{**r,'infrastructure_error':True} for r in cand])
        with self.assertRaises(ValueError):compare(lock,base,[{**r,'verifier':'custom'} for r in cand])


class ReportingTests(unittest.TestCase):
    def test_partial_runs_are_provisional_and_hidden_metadata_never_exported(self):
        from lab.report import summarize
        rows=[{'task_id':'private-id','archetype':'private-template','arm':'standard','split':'heldout',
            'model':'qwen','repetition':0,'result':{'passed':False,'accounting_complete':True,
            'failure_tag':'REASONING','metrics':{'prompt_tokens':100,'completion_tokens':10,'cost_usd':.01},
            'trace':'/private/trace','hidden':'answer'}}]
        report=summarize(rows)
        self.assertTrue(report['provisional'])
        self.assertIsNone(report['cells'][0]['tokens_per_solve'])
        self.assertNotIn('private-id',json.dumps(report))
        self.assertNotIn('/private/trace',json.dumps(report))

    def test_missing_compaction_invalidates_context_claim(self):
        from lab.report import summarize
        rows=[{'task_id':'x','archetype':'ctx','arm':'standard','split':'dev','model':'qwen','repetition':r,
            'result':{'passed':True,'accounting_complete':True,'failure_tag':None,
                'requires_compaction':True,'compaction_events_observed':0,
                'metrics':{'prompt_tokens':10,'completion_tokens':2,'cost_usd':.01}}} for r in range(5)]
        self.assertTrue(summarize(rows)['provisional'])
