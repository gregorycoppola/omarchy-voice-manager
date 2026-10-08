from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from speech import history
from speech.grammar import Grammar
from speech_preview import Preview


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'observations.sqlite3'
        self.db = sqlite3.connect(self.path)
        self.addCleanup(self.db.close)
        self.db.execute('CREATE TABLE observations(id TEXT PRIMARY KEY, created TEXT, data TEXT, review TEXT, intended TEXT)')

    def test_completed_attempt_and_review_survive_reopen(self):
        parsed = Grammar({}).parse('switch to workspace three')
        observation = {'id':'one','source':'typed','parsed':parsed}
        history.save(self.db, observation)
        with self.db:
            self.db.execute("UPDATE observations SET review='correct',intended='workspace three'")
        history.save(self.db, observation)
        with closing(sqlite3.connect(self.path)) as reopened:
            records = list(history.rows(reopened))
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record['input']['text'], 'switch to workspace three')
        self.assertEqual(record['parsed'], parsed)
        self.assertEqual(record['intents'][0]['intent'], parsed['candidates'][0]['intent'])
        self.assertEqual(record['outcome']['status'], 'matched')
        self.assertEqual(record['review'], 'correct')
        self.assertEqual(record['intended'], 'workspace three')

    def test_existing_unrecognized_and_empty_asr_are_preserved(self):
        for i, text in enumerate(['', 'not a supported sentence']):
            parsed = Grammar({}).parse(text)
            self.db.execute("INSERT INTO observations VALUES(?, '2026-10-06', ?, NULL, NULL)",
                            (str(i),json.dumps({'id':str(i),'source':'microphone','parsed':parsed})))
        self.db.commit()
        records = list(history.rows(self.db))
        self.assertEqual([r['input']['text'] for r in records], ['', 'not a supported sentence'])
        self.assertTrue(all(r['intents']==[] for r in records))
        self.assertTrue(all(r['outcome']['status']=='unrecognized' for r in records))

    def test_interrupted_capture_is_visible_after_restart(self):
        history.save(self.db, {'id':'one','source':'microphone','audio':'retained.wav',
                     'parsed':{'transcript':None,'candidates':[],'status':'pending'},
                     'outcome':{'status':'transcribing','execution':'not_executed'}})
        history.recover(self.db)
        record = next(history.rows(self.db))
        self.assertEqual(record['outcome']['status'],'interrupted')
        self.assertIsNone(record['input']['text'])
        self.assertEqual(record['input']['audio'],'retained.wav')

    def test_parser_exception_keeps_typed_input(self):
        fake = SimpleNamespace(db=self.db, phase='idle', generation=0, intended=Mock(),
                               render_result=Mock(), make_grammar=Mock(side_effect=ValueError('parse failed')))
        fake.show_result=lambda o,g,grammar=None:Preview.show_result(fake,o,g,grammar)
        entry=Mock();entry.get_text.return_value='  My original words!  '
        with patch('speech_preview.capture_window_context',return_value={}):
            Preview.test_text(fake,entry)
        record=next(history.rows(self.db))
        self.assertEqual(record['input']['text'],'  My original words!  ')
        self.assertEqual(record['outcome']['status'],'error')
        self.assertEqual(record['outcome']['error'],'parse failed')

    def test_browsing_and_review_do_not_execute_or_add_attempts(self):
        for i in range(2):
            history.save(self.db,{'id':str(i),'source':'typed','parsed':Grammar({}).parse('volume down')})
        fake=SimpleNamespace(db=self.db,phase='idle',latest=None,intended=Mock(),
                             render_result=Mock(),history_label=Mock(),status=Mock())
        with patch('speech_preview.subprocess.Popen') as launch:
            Preview.browse_history(fake,0)
            self.assertEqual(fake.latest,'1')
            Preview.browse_history(fake,-1)
            self.assertEqual(fake.latest,'0')
            fake.intended.get_text.return_value='volume up'
            Preview.review(fake,'incorrect')
            launch.assert_not_called()
        records=list(history.rows(self.db))
        self.assertEqual(len(records),2)
        self.assertEqual(records[0]['review'],'incorrect')
        self.assertEqual(records[0]['intended'],'volume up')

    def test_asr_failure_is_saved_without_inventing_text(self):
        fake=SimpleNamespace(db=self.db,phase='transcribing',generation=1,intended=Mock(),
                             render_result=Mock(),fail=Mock())
        fake.show_result=lambda o,g,grammar=None:Preview.show_result(fake,o,g,grammar)
        observation={'id':'failed','source':'microphone','audio':'saved.wav',
                     'parsed':{'transcript':None,'status':'pending','candidates':[]}}
        Preview.recording_failed(fake,observation,'ASR worker stopped',1)
        record=next(history.rows(self.db))
        self.assertIsNone(record['input']['text'])
        self.assertEqual(record['input']['audio'],'saved.wav')
        self.assertEqual(record['outcome']['error'],'ASR worker stopped')
        self.assertEqual(record['intents'],[])

    def test_closing_capture_preserves_interruption_and_stops_workers(self):
        observation={'id':'cancelled','source':'microphone',
                     'parsed':{'transcript':None,'status':'pending','candidates':[]}}
        fake=SimpleNamespace(db=self.db,active_observation=observation,generation=1,
                             recorder=Mock(),model=Mock(),quit=Mock())
        fake.recorder.poll.return_value=None;fake.model.poll.return_value=None
        Preview.close(fake)
        self.assertEqual(next(history.rows(self.db))['outcome']['status'],'interrupted')
        fake.recorder.kill.assert_called_once()
        fake.model.terminate.assert_called_once()
        fake.quit.assert_called_once()
