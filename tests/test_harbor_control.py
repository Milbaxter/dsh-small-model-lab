import copy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import tarfile
import unittest
from unittest.mock import patch

from lab.harbor_control import HARBOR_COMMIT, COMPARISON_FILES, ROOT, file_digest, normalize, prepare, private_gateway
from lab.budget import Ledger


class GatewayAddressTests(unittest.TestCase):
    def test_only_explicit_private_bridge_address_is_accepted(self):
        self.assertEqual(private_gateway('http://172.17.0.1:18080/v1'),'172.17.0.1')
        for url in ('http://0.0.0.0:18080/v1','http://8.8.8.8:18080/v1',
                    'http://127.0.0.1:18080/v1','http://172.17.0.1:80/v1'):
            with self.assertRaises(ValueError):private_gateway(url)


@unittest.skipUnless(importlib.util.find_spec('harbor'),'Requires the pinned Harbor environment')
class HarborControlTests(unittest.TestCase):
    def test_preparation_keeps_full_suite_oracles_first_and_interleaves_arms(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);dataset=root/'dataset';bundle=root/'runtime.tar.gz'
            with tarfile.open(bundle,'w:gz') as archive:
                for name in COMPARISON_FILES:archive.add(ROOT/name,arcname='lab/'+name)
            task_dir=dataset/'tasks'/'fixture';task_dir.mkdir(parents=True)
            config=task_dir/'task.toml';config.write_text('[environment]\ncpus=2\nmemory_mb=512\n[agent]\ntimeout_sec=1200\n')
            task={'id':'fixture','task_config_sha256':file_digest(config),'cpus':2,'memory_mib':512,
                'gpus':0,'storage_mib':10240,'agent_timeout_sec':1200}
            lock={'tasks':[task],'k':5,'dataset_commit':'dataset','minimum_resource_multiplier':3,
                'max_required_cpus':6,'max_required_memory_mib':1536}
            with patch('lab.harbor_control.checkout',side_effect=['dataset',HARBOR_COMMIT,'source']):
                m=prepare(lock,dataset,bundle,'http://172.17.0.1:18080/v1',root/'harbor',root/'state',{'model':'fixture'})
            self.assertEqual(len(m['trials']),11)
            self.assertEqual(m['trials'][0]['arm'],'oracle')
            a,b=m['trials'][1:3]
            self.assertEqual(a['evaluation_fingerprint'],b['evaluation_fingerprint'])
            self.assertEqual(a['config']['environment']['override_cpus'],6)
            self.assertEqual(a['config']['environment']['override_memory_mb'],1536)
            self.assertEqual(a['config']['agent']['kwargs']['wall_seconds'],1200)
            self.assertEqual(m['trials'][3]['arm'],'standard+autonomy-policy')

    def fixture(self,root):
        from harbor.models.trial.config import TrialConfig
        from harbor.models.trial.result import TrialResult
        now=datetime.now(timezone.utc)
        config=TrialConfig(task={'path':root/'task'},trial_name='fixture',trials_dir=root/'trials',
            agent={'import_path':'lab.harbor_agent:DSHAgent','kwargs':{'arm':'standard'}})
        metadata={'arm':'standard','repetition':0,'runtime_bundle_sha256':'bundle',
            'gateway_run_id':'run','accounting_complete':True}
        result=TrialResult(task_name='task',trial_name='fixture',trial_uri='file:///fixture',
            task_id={'path':root/'task'},task_checksum='fixture',config=config,
            agent_info={'name':'dsh-small-model-lab','version':'0.1.7-rc.2'},finished_at=now,
            verifier={'started_at':now,'finished_at':now},verifier_result={'rewards':{'reward':1}},
            agent_result={'n_input_tokens':10,'n_output_tokens':2,'cost_usd':.01,'metadata':metadata})
        traces=root/'runs';traces.mkdir()
        trace=traces/(Ledger.digest('run')+'.jsonl')
        trace.write_text(json.dumps({'kind':'request','payload':{}})+'\n'+json.dumps({'kind':'usage',
            'usage':{'prompt_tokens':10,'completion_tokens':2,'cost':.01}})+'\n')
        trial={'task_id':'task','arm':'standard','repetition':0,'evaluation_fingerprint':'conditions',
            'config':config.model_dump(mode='json')}
        manifest={'conditions':{'runtime_bundle_sha256':'bundle','score_label':'Test fixture only'},'lock':{'dataset_commit':'dataset'}}
        return result.model_dump(mode='json'),trial,manifest

    def test_official_reward_is_bound_to_config_runtime_and_trusted_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);result,trial,manifest=self.fixture(root)
            normalized=normalize(result,trial,manifest,root)
            self.assertEqual(normalized['reward'],1);self.assertEqual(normalized['tokens'],12)
            changed=copy.deepcopy(result);changed['agent_result']['cost_usd']=0
            with self.assertRaisesRegex(ValueError,'trusted gateway'):normalize(changed,trial,manifest,root)
            changed=copy.deepcopy(result);changed['config']['verifier']['disable']=True
            with self.assertRaisesRegex(ValueError,'configuration'):normalize(changed,trial,manifest,root)
            changed=copy.deepcopy(result);changed['verifier_result']['rewards']={}
            with self.assertRaisesRegex(ValueError,'official binary'):normalize(changed,trial,manifest,root)
            changed=copy.deepcopy(result);changed['agent_result']['metadata']['runtime_bundle_sha256']='different'
            with self.assertRaisesRegex(ValueError,'runtime differs'):normalize(changed,trial,manifest,root)

    def test_model_timeout_keeps_official_verifier_outcome_but_infrastructure_does_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);result,trial,manifest=self.fixture(root)
            result['exception_info']={'exception_type':'AgentTimeoutError','exception_message':'timeout',
                'exception_traceback':'fixture','occurred_at':datetime.now(timezone.utc).isoformat()}
            self.assertTrue(normalize(result,trial,manifest,root)['agent_timeout'])
            result['exception_info']['exception_type']='VerifierTimeoutError'
            with self.assertRaisesRegex(ValueError,'Infrastructure'):normalize(result,trial,manifest,root)
