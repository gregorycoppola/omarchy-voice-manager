from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from speech import learning,openai_fallback,history
from speech.grammar import Grammar
from speech_preview import Preview

class LearningTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'grammar/current.json'
        self.audit=patch('speech.learning.audit.append').start();self.addCleanup(patch.stopall)
        self.base=Grammar({})

    def test_both_categories_repeat_locally_preserve_input_and_disable(self):
        for source,kind in [('list all open windows','phrase_rule'),("let's go open windows",'recognition_correction')]:
            proposal=dict(kind=kind,input_phrase=source,canonical_phrase='list all windows',rationale='confirmed')
            expected=self.base.parse('list all windows')
            rule=learning.approve(proposal,source,expected,self.base,'observation',self.path)
            parsed=learning.LearnedGrammar(self.base,self.path).parse(source)
            self.assertEqual(parsed['transcript'],source)
            self.assertEqual(parsed['learned_rule_id'],rule['id'])
            self.assertEqual(parsed['learned_rule_kind'],kind)
            self.assertEqual(learning.meaning(parsed),learning.meaning(expected))
            self.assertEqual(learning.LearnedGrammar(self.base,self.path).parse('volume down')['method'],'clean_grammar')
            self.assertEqual(learning.LearnedGrammar(self.base,self.path).parse(source+' in workspace banana')['status'],'unrecognized')
            with self.assertRaises(ValueError):learning.approve(proposal,source,expected,self.base,'observation',self.path)
            learning.disable(rule['id'],self.path)
            self.assertEqual(learning.LearnedGrammar(self.base,self.path).parse(source)['status'],'unrecognized')
        self.assertEqual(len(list(self.path.parent.glob('grammar-versions/*.json'))),4)
        self.assertIn('rule_activated',[c.args[0] for c in self.audit.call_args_list])

    def test_rejects_unsupported_and_overlapping_mappings(self):
        for source,target in [('list all open windows','list windows in workspace two'),('volume down','volume up')]:
            with self.assertRaises(ValueError):
                learning.approve(dict(kind='phrase_rule',input_phrase=source,canonical_phrase=target,rationale='test'),source,self.base.parse(target),self.base,'o',self.path)
        self.assertFalse(self.path.exists())

    def test_mishearing_requires_confirmation_question_and_valid_canonical(self):
        reply={'status':'mishearing','canonical_text':'list all windows','clarification':'Did you mean list windows?'}
        self.assertEqual(openai_fallback.validate(reply,self.base)['status'],'matched')
        reply['clarification']=None
        with self.assertRaises(ValueError):openai_fallback.validate(reply,self.base)
        self.assertIsNone(openai_fallback.validate({'status':'unsupported','canonical_text':None,'clarification':'Workspace filter is unsupported.'},self.base))

    def test_ui_confirmation_saves_and_checks_repeat_without_execution(self):
        with closing(sqlite3.connect(':memory:')) as db:
            db.execute('CREATE TABLE observations(id TEXT PRIMARY KEY,created TEXT,data TEXT,review TEXT,intended TEXT)')
            original="let's go open windows"
            obs={'id':'o','source':'typed','parsed':self.base.parse(original),'llm':{'status':'mishearing'}}
            fake=SimpleNamespace(phase='ready',latest_observation=obs,db=db,mapping=Mock(),render_result=Mock(),status=Mock(),
                make_grammar=lambda context:learning.LearnedGrammar(self.base,self.path))
            fake.mapping.get_text.return_value='list all windows'
            approve=learning.approve
            with patch('speech_preview.learning.approve',side_effect=lambda *args:approve(*args,path=self.path)),patch('speech_preview.subprocess.Popen') as execute:
                Preview.accept_mapping(fake,'recognition_correction')
            execute.assert_not_called()
            record=next(history.rows(db))
            self.assertEqual(record['outcome']['status'],'learned')
            self.assertEqual(record['parsed']['status'],'unrecognized')
            self.assertEqual(record['confirmed']['choice'],'recognition_correction')
            self.assertIn('rule_repeat_verified',[r[0] for r in db.execute('SELECT kind FROM events')])
