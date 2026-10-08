import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from runtime import VoiceRuntime
from settings import Settings
from speech.grammar import Grammar
from speech.execution import execution_result

class VoiceExecutionTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.app=VoiceRuntime(data=self.root,status_path=self.root/'status.json')
        self.database=self.root/'voice.sqlite3';self.ident='a'*32
        self.context={'active':{'workspace':{'id':2}},'clients':[]}
        self.apps=SimpleNamespace(apps=(),expansions=(),targets={})
        self.windows=SimpleNamespace(words=(),expansions=(),targets={})
        self.parsed=Grammar(self.context,self.apps,self.windows).parse('open github in a new tab')
        with sqlite3.connect(self.database) as db:
            db.execute('CREATE TABLE observations(id TEXT,created TEXT,data TEXT)')
            db.execute('INSERT INTO observations VALUES(?,datetime("now"),?)',(self.ident,json.dumps({
                'mode':'execute','source':'microphone','context':self.context,'parsed':self.parsed})))
        for context in [patch.object(self.app,'voice_database',return_value=self.database),
                        patch.object(self.app,'publish'),patch.object(self.app,'focused_monitor',return_value='test'),
                        patch('runtime.discover_installed_apps',return_value=self.apps),
                        patch('runtime.inject_windows',return_value=self.windows)]:
            context.start();self.addCleanup(context.stop)

    def outcome(self):
        with sqlite3.connect(self.database) as db:return db.execute('SELECT status,message FROM executions').fetchone()

    def test_debug_explicitly_disables_execution(self):
        Settings(self.root/'settings.json').set_voice_debug(True)
        with patch('runtime.threading.Thread') as worker:self.app.execute_voice(self.ident)
        worker.assert_not_called();self.assertEqual(self.outcome()[0],'error')
        self.assertIn('Debug mode',self.outcome()[1])

    def test_normal_mode_is_default(self):
        self.assertFalse(Settings(self.root/'settings.json').voice_debug)
        with patch('runtime.threading.Thread') as worker:self.app.execute_voice(self.ident)
        worker.assert_called_once()

    def test_off_dispatches_exact_new_tab_binding_once(self):
        Settings(self.root/'settings.json').set_voice_debug(False)
        with patch('runtime.threading.Thread') as worker:
            self.app.execute_voice(self.ident);self.app.execute_voice(self.ident)
        worker.assert_called_once()
        kwargs=worker.call_args.kwargs['kwargs']
        self.assertEqual(kwargs['source'],'voice')
        self.assertEqual(kwargs['prepared_result'].command,'site-new:github')
        self.assertEqual(self.outcome()[0],'dispatched')

    def test_debug_recording_never_becomes_executable(self):
        Settings(self.root/'settings.json').set_voice_debug(False)
        with sqlite3.connect(self.database) as db:
            saved=json.loads(db.execute('SELECT data FROM observations').fetchone()[0]);saved['mode']='debug'
            db.execute('UPDATE observations SET data=?',(json.dumps(saved),))
        with patch('runtime.threading.Thread') as worker:self.app.execute_voice(self.ident)
        worker.assert_not_called();self.assertEqual(self.outcome()[0],'error')

    def test_changed_meaning_is_rejected(self):
        Settings(self.root/'settings.json').set_voice_debug(False)
        with sqlite3.connect(self.database) as db:
            saved=json.loads(db.execute('SELECT data FROM observations').fetchone()[0])
            saved['parsed']['transcript']='open github'
            db.execute('UPDATE observations SET data=?',(json.dumps(saved),))
        with patch('runtime.threading.Thread') as worker:self.app.execute_voice(self.ident)
        worker.assert_not_called();self.assertIn('changed',self.outcome()[1])

    def test_numeric_executor_binding(self):
        result=execution_result(Grammar().parse('switch to workspace nineteen'))
        self.assertEqual(result.command,'workspace:switch:19')

    def test_setting_preserves_existing_preferences(self):
        settings=Settings(self.root/'settings.json');settings.set_layout_excluded_classes(['keep'])
        settings.set_voice_debug(False);loaded=Settings(self.root/'settings.json')
        self.assertFalse(loaded.voice_debug);self.assertEqual(loaded.layout_excluded_classes,['keep'])

    def test_validated_cloud_wording_dispatches(self):
        original={'status':'unrecognized','transcript':'please open github for me','candidates':[]}
        canonical='open github in a new tab'
        cloud={'status':'interpreted','reply':{'status':'interpreted','canonical_text':canonical,'clarification':None},'parsed':self.parsed}
        with sqlite3.connect(self.database) as db:
            db.execute('UPDATE observations SET data=?',(json.dumps({'mode':'execute','source':'microphone','context':self.context,'parsed':original,'llm':cloud}),))
        with patch('runtime.threading.Thread') as worker:self.app.execute_voice(self.ident)
        worker.assert_called_once()
        self.assertEqual(self.app.state['transcript'],original['transcript'])

    def test_cloud_mishearing_does_not_execute(self):
        with sqlite3.connect(self.database) as db:
            db.execute('UPDATE observations SET data=?',(json.dumps({'mode':'execute','source':'microphone','context':self.context,
                'parsed':{'status':'unrecognized','transcript':'unclear words','candidates':[]},
                'llm':{'status':'mishearing','parsed':self.parsed}}),))
        with patch('runtime.threading.Thread') as worker:self.app.execute_voice(self.ident)
        worker.assert_not_called()

    def test_duplicate_browser_names_offer_choice_before_execution(self):
        from grammar_engine import Word
        self.windows.words=tuple(Word(k,'chromium',('chromium',)) for k in ('one','two'))
        self.windows.targets={k:{'title':title,'class':'chromium','workspace':{'id':1}} for k,title in [('one','Docs'),('two','Mail')]}
        parsed=Grammar(self.context,self.apps,self.windows).parse('focus on chromium')
        self.assertEqual(parsed['status'],'ambiguous')
        with sqlite3.connect(self.database) as db:
            db.execute('UPDATE observations SET data=?',(json.dumps({'mode':'execute','source':'microphone','context':self.context,'parsed':parsed}),))
        with patch('runtime.threading.Thread') as worker:
            self.app.execute_voice(self.ident)
            worker.assert_not_called()
            self.assertEqual(self.app.state['state'],'Choose')
            choices=self.app.state['clarification']['choices']
            self.assertEqual(len(choices),2)
            self.app.choose_window(choices[1]['token'])
            worker.assert_called_once()
            self.assertEqual(worker.call_args.kwargs['kwargs']['prepared_result'].command,'focus-window:two')

    def test_terminal_category_uses_window_choices(self):
        from grammar_engine import Word
        self.windows.words=tuple(Word(k,title,(title,)) for k,title in [('one','editor'),('two','logs')])
        self.windows.targets={k:{'class':'Alacritty','title':k,'workspace':{'id':1}} for k in ('one','two')}
        grammar=Grammar(self.context,self.apps,self.windows)
        from speech.openai_fallback import validate
        for phrase in ['focus terminal','focus on terminal','focus on the terminal']:
            parsed=grammar.parse(phrase)
            self.assertEqual(parsed['status'],'ambiguous')
            result=validate({'status':'interpreted','canonical_text':phrase,'clarification':None},grammar)
            self.assertEqual(result['status'],'ambiguous')
        self.windows.words=self.windows.words[:1]
        self.assertEqual(Grammar(self.context,self.apps,self.windows).parse('focus on the terminal')['status'],'matched')
