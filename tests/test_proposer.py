import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from lab.proposer import development_packet, leakage_scan, policy_module, validate_proposal


class ProposerTests(unittest.TestCase):
    def test_only_dev_and_explicit_visible_fields_are_exported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'tasks').mkdir()
            for split in ('dev','heldout','transfer'):
                task={'task_id':split,'split':split,'family':'completion','stages':[{'instruction':split+' prompt'}],
                    'workspace':{'input.txt':'visible'},'hidden':{'answer':'NEVER_EXPORT'},'reference':'NEVER_EXPORT','grader':'NEVER_EXPORT'}
                (root/'tasks'/f'{split}.json').write_text(json.dumps(task))
            db=sqlite3.connect(root/'trials.sqlite')
            db.execute('CREATE TABLE trials(task_id,split,arm,status,result,updated)')
            for n,split in enumerate(('dev','heldout','transfer')):
                result={'passed':False,'failure_tag':'REASONING','metrics':{},'trace':str(root/'absent')}
                db.execute('INSERT INTO trials VALUES(?,?,?,?,?,?)',(split,split,'standard','complete',json.dumps(result),n))
            db.commit();db.close()
            packet=development_packet(root,root/'trials.sqlite',champion='standard')
            text=json.dumps(packet)
            self.assertEqual(len(packet['examples']),1)
            self.assertNotIn('NEVER_EXPORT',text)
            self.assertNotIn('heldout prompt',text)
            self.assertNotIn('transfer prompt',text)

    def test_leakage_and_executable_payload_are_handled_as_text(self):
        task={'split':'dev','workspace':{'solution.py':''},'stages':[{'instruction':'Repair task lab-0123456789 with care and exact accounting.'}]}
        safe='Inspect the current state before making a focused change. Check relevant behavior afterward and distinguish observed results from assumptions. Stop repeating unsuccessful actions and investigate the cause.'
        self.assertTrue(leakage_scan(safe,[task])['passed'])
        self.assertFalse(leakage_scan(safe+' Modify solution.py for lab-0123456789.',[task])['passed'])
        module=policy_module('`); process.exit(1); //')
        self.assertIn('text:"`); process.exit(1); //"',module)
        with self.assertRaises(ValueError):validate_proposal({'policy':'Only a policy'})
