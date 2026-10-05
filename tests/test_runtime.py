import personal_store
"""Windowless runtime routing, confirmation identity, and lifecycle checks."""
import json
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import Mock, patch

from runtime import VoiceRuntime


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.data = Path(directory.name)
        self.app = VoiceRuntime(self.data, self.data / 'status.json')
        self.app.busy = True
        self.idle = patch('runtime.GLib.idle_add', side_effect=lambda fn, *args: fn(*args))
        self.idle.start()
        self.addCleanup(self.idle.stop)
        popup = patch.object(self.app, 'show_correction')
        popup.start()
        self.addCleanup(popup.stop)

    def transcribe(self, text, commands=True, context=None):
        with patch.object(self.app, 'execute', return_value='Done') as execute:
            self.app.interpret(text, context, commands, source='speech')
        return execute

    def test_fuzzy_parse_saves_before_running_and_preserves_structure(self):
        execute = self.transcribe('open dis cord')
        execute.assert_called_once_with('discord', None, None)
        self.assertEqual(self.app.state['intent']['arguments']['application'], 'discord')
        self.assertEqual(personal_store.load(self.data / 'aliases.json')['aliases'], {'open dis cord': 'discord'})
        self.assertEqual(self.app.state['state'], 'Ready')
        self.assertGreater(self.app.state['completed_at'], 0)
        self.assertFalse(self.app.busy)
        self.assertEqual((self.data / 'status.json').stat().st_mode & 0o777, 0o600)

    def test_retry_and_negation_never_run_or_learn(self):
        for text, commands in [('open chrome', False), ("don't open chrome", True)]:
            self.transcribe(text, commands).assert_not_called()
            self.assertFalse((self.data / 'aliases.json').exists())

    def test_user_correction_dispatches_and_logs_original_words_without_learning(self):
        from corrections import Corrections
        Corrections(self.data / 'corrections.json').save('towel apps', 'tile the apps', 'apps:tile')
        context = {'active': {'workspace': {'id': 2}}}
        execute = self.transcribe('Towel apps.', context=context)
        execute.assert_called_once_with('apps:tile', context, None)
        self.assertEqual(self.app.state['transcript'], 'Towel apps.')
        self.assertFalse((self.data / 'aliases.json').exists())
        events = [json.loads(line) for line in (self.data / 'commands.jsonl').read_text().splitlines()]
        parsed = next(e for e in events if e['event'] == 'parsed')
        self.assertEqual(parsed['result']['method'], 'correction')
        self.assertEqual(parsed['result']['correction']['meant'], 'tile the apps')

    def test_user_correction_to_close_still_requires_terminal_confirmation(self):
        from corrections import Corrections
        Corrections(self.data / 'corrections.json').save('finish this', 'close this terminal', 'close:terminal_current')
        target = {'class': 'foot', 'address': '0x123', 'pid': 1, 'title': 'Busy terminal'}
        with patch('runtime.terminal_close_target', return_value=target), \
             patch('runtime.terminal_has_jobs', return_value=True):
            self.transcribe('finish this', context={'active': target}).assert_not_called()
        self.assertEqual(self.app.state['state'], 'Confirm')

    def test_failed_action_releases_busy_and_accepts_the_next_command(self):
        with patch.object(self.app, 'execute', side_effect=RuntimeError('Launcher failed')):
            self.app.interpret('open chrome', {}, True, source='speech')
        self.assertEqual(self.app.state['state'], 'Error')
        self.assertFalse(self.app.busy)
        self.transcribe('open chrome').assert_called_once()

    def test_confirmation_retains_target_and_rejects_stale_approval(self):
        target = {'class': 'foot', 'address': '0x123', 'pid': 1, 'title': 'Busy terminal'}
        context = {'active': target}
        with patch('runtime.terminal_close_target', return_value=target) as capture, \
             patch('runtime.terminal_has_jobs', return_value=True):
            self.transcribe('close this terminal', context=context).assert_not_called()
        capture.assert_called_once_with('close:terminal_current', context)
        self.assertEqual(self.app.state['state'], 'Confirm')
        token = self.app.pending[0]
        self.app.confirm('stale')
        self.assertIsNotNone(self.app.pending)
        with patch('runtime.threading.Thread') as thread:
            self.app.confirm(token)
            pending = thread.call_args.kwargs['args'][0]
        with patch.object(self.app, 'execute', return_value='Closed') as execute:
            self.app.run_confirmed(pending)
        execute.assert_called_once_with('close:terminal_current', target=target)
        self.assertIsNone(self.app.pending)
        self.assertIsNone(self.app.state['confirmation'])

    def test_cancelled_confirmation_cannot_be_replayed(self):
        self.app.offer_confirmation('close:terminal', {'class': 'foot'}, 'close terminal', False)
        token = self.app.pending[0]
        self.app.cancel(token)
        with patch('runtime.threading.Thread') as thread:
            self.app.confirm(token)
            thread.assert_not_called()


    def test_quit_waits_for_processing_and_then_stops(self):
        with patch.object(self.app, 'quit') as quit, patch('runtime.connection.close'):
            self.app.request_quit()
            quit.assert_not_called()
            self.app.complete('Ready', 'Done')
            quit.assert_called_once()
        self.assertEqual(self.app.state['state'], 'Stopped')


    def test_yes_no_only_answer_matching_pending_confirmation(self):
        target = {'class': 'foot', 'address': '0x123', 'pid': 1, 'title': 'Busy terminal'}
        self.app.offer_confirmation('close:terminal', target, 'close terminal', False)
        token = self.app.pending[0]
        with patch.object(self.app, 'confirm') as confirm:
            self.app.answer_confirmation('stale', 'yes')
            confirm.assert_not_called()
            self.app.answer_confirmation(token, 'yesterday')
            confirm.assert_not_called()
            self.assertEqual(self.app.state['state'], 'Confirm')
            self.app.busy = True
            self.app.interpret('yes please', {'confirmation_token': token}, source='speech')
            confirm.assert_called_once_with(token)
        self.app.answer_confirmation(token, 'no')
        self.assertIsNone(self.app.pending)
        self.assertEqual(self.app.state['state'], 'Ready')
