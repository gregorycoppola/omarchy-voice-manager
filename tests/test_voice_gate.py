from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock,patch
from speech_preview import Preview

class VoiceGateTests(unittest.TestCase):
    def test_delayed_start_after_release_cannot_open_microphone(self):
        with tempfile.TemporaryDirectory() as root:
            gate=Path(root)/'gate';gate.write_text('0')
            fake=SimpleNamespace(phase='ready')
            with patch('speech_preview.GATE',gate),patch('speech_preview.subprocess.Popen') as launch:
                Preview.start_recording(fake)
            launch.assert_not_called()

    def test_model_loading_never_starts_recording_later(self):
        with patch('speech_preview.subprocess.Popen') as launch:
            Preview.start_recording(SimpleNamespace(phase='loading'))
        launch.assert_not_called()

    def test_gate_closes_if_release_notification_is_lost(self):
        with tempfile.TemporaryDirectory() as root:
            gate=Path(root)/'gate';gate.write_text('0')
            fake=SimpleNamespace(phase='recording',record_generation=3,stop_recording=Mock())
            with patch('speech_preview.GATE',gate):self.assertFalse(Preview.check_gate(fake,3))
            fake.stop_recording.assert_called_once_with()

    def test_release_terminates_capture_before_transcription(self):
        fake=SimpleNamespace(phase='recording',recorder=Mock(),status=Mock(),finish_recording=Mock())
        with patch('speech_preview.threading.Thread') as thread:
            Preview.stop_recording(fake)
            fake.recorder.terminate.assert_called_once_with()
            thread.assert_called_once()
            self.assertEqual(fake.phase,'transcribing')
            Preview.stop_recording(fake)
            fake.recorder.terminate.assert_called_once_with()


class TypedGrammarTests(unittest.TestCase):
    def test_typing_uses_speech_grammar_without_enabling_speech(self):
        from speech.grammar import Grammar
        import sqlite3
        import json
        for phase in ('idle', 'loading', 'error', 'ready'):
            with self.subTest(phase=phase), sqlite3.connect(':memory:') as db:
                db.execute('CREATE TABLE observations(id TEXT PRIMARY KEY, created TEXT, data TEXT, review TEXT, intended TEXT)')
                grammar=Grammar({})
                fake=SimpleNamespace(phase=phase, generation=0, db=db, intended=Mock(),
                    make_grammar=lambda context:grammar, render_result=Mock(), window=Mock(), raise_preview=Mock())
                fake.show_result=lambda observation,generation,grammar=None:Preview.show_result(fake,observation,generation,grammar)
                entry=Mock();entry.get_text.return_value='switch to workspace three'
                with patch('speech_preview.capture_window_context',return_value={}), patch('speech_preview.subprocess.Popen') as launch:
                    Preview.test_text(fake,entry)
                saved=json.loads(db.execute('SELECT data FROM observations').fetchone()[0])
                expected=grammar.parse(entry.get_text())
                saved['parsed'].pop('parse_ms');expected.pop('parse_ms')
                self.assertEqual(saved['parsed'],expected)
                self.assertEqual(saved['parsed']['status'],'matched')
                self.assertEqual(saved['mode'],'debug')
                self.assertEqual(saved['source'],'typed')
                self.assertEqual(fake.phase,phase)
                launch.assert_not_called()

    def test_spoken_result_is_preview_only_even_with_old_execute_mode(self):
        from contextlib import closing
        import sqlite3
        import json
        with closing(sqlite3.connect(':memory:')) as db:
            db.execute('CREATE TABLE observations(id TEXT PRIMARY KEY, created TEXT, data TEXT, review TEXT, intended TEXT)')
            fake=SimpleNamespace(phase='transcribing',generation=1,db=db,intended=Mock(),
                                 render_result=Mock(),window=Mock())
            observation={'id':'trial','source':'microphone','mode':'execute',
                         'parsed':{'status':'matched'}}
            with patch('speech_preview.subprocess.Popen') as launch:
                Preview.show_result(fake,observation,1)
            launch.assert_not_called()
            fake.window.present.assert_not_called()
            fake.render_result.assert_called_once()
            saved=json.loads(db.execute('SELECT data FROM observations').fetchone()[0])
            self.assertEqual(saved['mode'],'debug')
            self.assertEqual(fake.phase,'ready')
