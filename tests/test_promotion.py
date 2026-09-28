import unittest
from lab.promotion import Protocol, decide


class PromotionTests(unittest.TestCase):
    def fixture(self):
        protocol=Protocol(dev_tasks=4,heldout_tasks=4,transfer_tasks=4)
        champion=[];candidate=[];control=[]
        for model in ('qwen','llama'):
            for split in (('dev','heldout','transfer') if model=='qwen' else ('transfer',)):
                for t in range(4):
                    for r in range(5):
                        common={'model':model,'split':split,'task_id':str(t),'repetition':r,
                            'accounting_complete':True,'evaluation_fingerprint':'pinned','tokens':100}
                        champion.append({**common,'passed':r==0})
                        candidate.append({**common,'passed':True})
                        control.append({**common,'passed':r==0,'matched_budget_verified':True})
        return dict(champion_rows=champion,candidate_rows=candidate,control_rows=control,primary_model='qwen',protocol=protocol,
            leakage={'passed':True,'candidate_sha256':'candidate'},
            review={'decision':'accept','separate_request':True,'model':'openai/gpt-6-astra','candidate_sha256':'candidate'},
            terminal_evidence={'independent_gate_passed':True,'candidate_sha256':'candidate',
                'reference':'original-plain-dsh','full_frozen_coverage':True})

    def test_all_gates_required_and_missing_transfer_is_not_a_pass(self):
        args=self.fixture();self.assertEqual(decide(**args)['decision'],'promote')
        args['candidate_rows']=[r for r in args['candidate_rows'] if r['model']=='qwen']
        self.assertFalse(decide(**args)['checks']['two_model_transfer'])
        self.assertNotEqual(decide(**args)['decision'],'promote')

    def test_cannot_promote_private_gain_without_terminal_or_independent_review(self):
        args=self.fixture();args['terminal_evidence']={}
        self.assertNotEqual(decide(**args)['decision'],'promote')
        args=self.fixture();args['review']['candidate_sha256']='another-candidate'
        self.assertNotEqual(decide(**args)['decision'],'promote')

    def test_mismatched_conditions_and_incomplete_pairs_fail_closed(self):
        args=self.fixture();args['candidate_rows'][0]['evaluation_fingerprint']='changed-model'
        self.assertEqual(decide(**args)['decision'],'insufficient_evidence')
        args=self.fixture();args['candidate_rows'].pop()
        self.assertEqual(decide(**args)['decision'],'insufficient_evidence')

    def test_more_tokens_without_pareto_improvement_is_rejected(self):
        args=self.fixture()
        for row in args['candidate_rows']:row['tokens']=1000
        self.assertFalse(decide(**args)['checks']['token_pareto'])
