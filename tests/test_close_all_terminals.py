import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from intent_matching import IntentMatcher
from os_actions import all_terminal_targets, close_terminals
from runtime import VoiceRuntime
from settings import Settings

A = dict(address='0x1', pid=1, stableId='one', workspace={'id': 1}, **{'class': 'foot'})
B = dict(address='0x2', pid=2, stableId='two', workspace={'id': 3}, **{'class': 'Alacritty'})
C = dict(address='0x3', pid=3, stableId='three', **{'class': 'chromium'})


class CloseAllTerminalsTests(unittest.TestCase):
    def test_shared_grammar_canonical_plan_and_no_fuzzy_or_negation(self):
        with tempfile.TemporaryDirectory() as directory:
            matcher = IntentMatcher(Path(directory) / 'aliases.json')
            for phrase in ('close all terminals', 'close all terminal windows', 'close every terminal'):
                result = matcher.parse(phrase)
                self.assertEqual(result.command, 'terminals:close')
                self.assertEqual(result.canonical_plan, [{'intent': 'window.close', 'arguments': {
                    'target': {'kind': 'all', 'value': 'all_terminals'}}}])
            for phrase in ('do not close all terminals', 'close all termnals'):
                self.assertNotEqual(matcher.parse(phrase).command, 'terminals:close')
            self.assertEqual(matcher.parse('close terminal').command, 'close:terminal')

    def test_snapshot_filters_nonterminals_and_includes_all_workspaces(self):
        targets = all_terminal_targets({'clients': [A, B, C, dict(A, address='0x4', mapped=False)]})
        self.assertEqual(targets, [A, B])
        self.assertIsNot(targets[0], A)
        with self.assertRaises(RuntimeError):
            all_terminal_targets(None)
        self.assertEqual(all_terminal_targets({'clients': [C]}), [])

    def test_new_windows_are_never_added_to_confirmed_batch(self):
        with patch('os_actions.run', return_value=json.dumps([A, B, C])), \
             patch('os_actions.close_terminal', return_value='Requested close') as close:
            self.assertIn('1 terminal', close_terminals([A]))
            close.assert_called_once_with(A)

    def test_changed_identity_prevents_entire_batch(self):
        with patch('os_actions.run', return_value=json.dumps([A, dict(B, pid=99)])), \
             patch('os_actions.close_terminal') as close:
            with self.assertRaisesRegex(RuntimeError, 'No windows were closed'):
                close_terminals([A, B])
            close.assert_not_called()

    def test_closed_targets_skipped_and_partial_failure_reported(self):
        with patch('os_actions.run', return_value=json.dumps([B])), \
             patch('os_actions.close_terminal', return_value='Requested close') as close:
            close_terminals([A, B])
            close.assert_called_once_with(B)
        with patch('os_actions.run', return_value=json.dumps([A, B])), \
             patch('os_actions.close_terminal', side_effect=['Requested close', RuntimeError('changed')]):
            with self.assertRaisesRegex(RuntimeError, 'after requesting 1'):
                close_terminals([A, B])

    def test_runtime_batch_confirmation_cancel_and_dispatch(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch('runtime.GLib.idle_add', side_effect=lambda fn, *args: fn(*args)), \
             patch('runtime.terminal_has_jobs', return_value=True), \
             patch('runtime.close_terminals', return_value='Requested closes') as close:
            root = Path(directory)
            app = VoiceRuntime(root, root / 'status.json')
            app.interpret('close all terminals', {'clients': [A, B, C]})
            self.assertEqual(app.state['state'], 'Confirm')
            self.assertEqual(app.pending[2], [A, B])
            self.assertIn('2 terminals', app.state['confirmation']['title'])
            close.assert_not_called()
            token = app.pending[0]
            app.cancel(token)
            with patch('runtime.threading.Thread') as thread:
                app.confirm(token)
                thread.assert_not_called()
            app.interpret('close all terminals', {'clients': [A, B, C]})
            with patch('runtime.threading.Thread') as thread:
                app.confirm(app.pending[0])
                pending = thread.call_args.kwargs['args'][0]
            app.run_confirmed(pending)
            close.assert_called_once_with([A, B])

    def test_idle_empty_unknown_and_disabled_confirmation(self):
        for jobs, enabled, expected_confirmation in ((False, True, False), (None, True, True), (True, False, False)):
            with self.subTest(jobs=jobs, enabled=enabled), tempfile.TemporaryDirectory() as directory, \
                 patch('runtime.GLib.idle_add', side_effect=lambda fn, *args: fn(*args)), \
                 patch('runtime.terminal_has_jobs', return_value=jobs), \
                 patch('runtime.close_terminals', return_value='Requested closes') as close:
                root = Path(directory)
                Settings(root / 'settings.json').set_confirm_terminal_close(enabled)
                app = VoiceRuntime(root, root / 'status.json')
                app.interpret('close all terminals', {'clients': [A, B]})
                self.assertEqual(app.state['state'] == 'Confirm', expected_confirmation)
                self.assertEqual(close.called, not expected_confirmation)
        with patch('os_actions.run') as run:
            self.assertIn('No open', close_terminals([]))
            run.assert_not_called()
