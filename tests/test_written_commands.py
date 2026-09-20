"""Written input shares the logical parser but bypasses speech and its corrections."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from corrections import Corrections
from runtime import VoiceRuntime


class WrittenTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.app = VoiceRuntime(self.root, self.root / 'status.json')
        self.context = {'active': {'address': '0x1', 'monitor': 0, 'workspace': {'id': 1}}, 'clients': []}
        for context in [patch('runtime.GLib.idle_add', side_effect=lambda fn, *a: fn(*a)),
                        patch('runtime.capture_window_context', return_value=self.context),
                        patch.object(self.app, 'focused_monitor', return_value='eDP-1')]:
            context.start()
            self.addCleanup(context.stop)

    def submit(self, text):
        token = self.app.pending_written['token']
        with patch('runtime.threading.Thread') as worker:
            self.app.submit_written(json.dumps(dict(token=token, text=text)))
        worker.assert_called_once()
        kwargs = worker.call_args.kwargs
        kwargs['target'](*kwargs['args'])

    def test_keyboard_mode_without_model_keeps_original_context(self):
        self.assertIsNone(self.app.model)
        self.app.type_command()
        self.assertEqual(self.app.state['state'], 'TextEntry')
        self.context['active']['monitor'] = 9
        self.assertEqual(self.app.pending_written['context']['active']['monitor'], 0)
        with patch('runtime.save_transcript') as speech, patch.object(self.app, 'execute', return_value='Opened') as execute:
            self.submit('open chrome')
        speech.assert_not_called()
        self.assertEqual(execute.call_args.args[0], 'browser')
        self.assertEqual(execute.call_args.args[1]['active']['monitor'], 0)
        self.assertEqual(self.app.state['input_source'], 'written')
        self.assertEqual(self.app.state['written'], 'open chrome')
        self.assertIsNone(self.app.pending_written)

    def test_written_bypasses_speech_corrections_and_does_not_train_speech_aliases(self):
        Corrections(self.root / 'corrections.json').save('open chrome', 'hide all apps', 'apps:hide')
        self.app.type_command()
        with patch.object(self.app, 'execute', return_value='Opened') as execute:
            self.submit('open chrome')
        self.assertEqual(execute.call_args.args[0], 'browser')
        self.app.type_command()
        with patch.object(self.app, 'execute', return_value='Opened'):
            self.submit('open dis cord')
        self.assertFalse((self.root / 'aliases.json').exists())

    def test_unparsed_text_stays_in_dropdown_without_speech_question(self):
        self.app.type_command()
        with patch.object(self.app, 'offer_correction') as correction, patch.object(self.app, 'execute') as execute:
            self.submit('purple asparagus dances')
        correction.assert_not_called()
        execute.assert_not_called()
        self.assertEqual(self.app.state['state'], 'TextEntry')
        self.assertEqual(self.app.state['written_entry']['text'], 'purple asparagus dances')
        self.assertIsNotNone(self.app.pending_written)

    def test_shortcut_again_and_voice_do_not_replace_pending_input(self):
        self.app.type_command()
        original = self.app.pending_written
        with patch.object(self.app, 'cancel') as cancel, patch.object(self.app, 'start_recording') as record:
            self.app.type_command()
            self.app.press()
        self.assertIs(self.app.pending_written, original)
        cancel.assert_not_called()
        record.assert_not_called()

    def test_cancel_rejects_old_submission(self):
        self.app.type_command()
        old = self.app.pending_written['token']
        self.app.cancel(old)
        self.app.type_command()
        with patch('runtime.threading.Thread') as worker:
            self.app.submit_written(json.dumps(dict(token=old, text='open chrome')))
        worker.assert_not_called()
        self.assertNotEqual(self.app.pending_written['token'], old)


if __name__ == '__main__':
    unittest.main()
