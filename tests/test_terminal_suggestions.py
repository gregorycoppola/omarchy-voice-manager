from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from intent_matching import IntentMatcher
from runtime import VoiceRuntime
from window_vocabulary import inject_windows, terminal_suggestions

A = dict(address='0x1', pid=1, stableId='one', title='Fix layout | omarchy voice manager', **{'class': 'foot'})
B = dict(address='0x2', pid=2, stableId='two', title='Review tests | another project', **{'class': 'Alacritty'})


class TerminalSuggestionTests(unittest.TestCase):
    def test_each_suggestion_parses_to_its_captured_window_and_action(self):
        context = {'clients': [A, B]}
        rows = terminal_suggestions(context)
        self.assertEqual(len(rows), 8)
        self.assertEqual(rows[0]['text'], 'close the omarchy voice manager terminal')
        vocabulary = inject_windows(context)
        with tempfile.TemporaryDirectory() as directory:
            matcher = IntentMatcher(Path(directory) / 'aliases.json')
            for row in rows:
                parsed = matcher.parse(row['text'], vocabulary.expansions, use_corrections=False)
                self.assertEqual(parsed.command, row['command'])
                self.assertIn(dict(parsed.intent.arguments)['window'], vocabulary.targets)

    def test_ambiguous_names_and_nonterminal_windows_not_suggested(self):
        context = {'clients': [A, dict(B, title='Review tests | omarchy voice manager'),
                               dict(B, address='0x3', **{'class': 'chromium'})]}
        rows = terminal_suggestions(context)
        self.assertEqual(len(rows), 8)
        self.assertNotIn('close the omarchy voice manager terminal', [f for r in rows for f in r['forms']])
        self.assertIn('close the fix layout terminal', [r['text'] for r in rows])
        duplicate = dict(B, title=A['title'])
        self.assertEqual(terminal_suggestions({'clients': [A, duplicate]}), [])

    def test_closed_unmapped_and_missing_identity_are_excluded(self):
        self.assertEqual(terminal_suggestions(None), [])
        self.assertEqual(terminal_suggestions({'clients': []}), [])
        self.assertEqual(terminal_suggestions({'clients': [dict(A, mapped=False), dict(B, stableId=None)]}), [])

    def test_box_rebuilds_separate_dynamic_source_without_writing_history(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch('runtime.capture_window_context', side_effect=[{'clients': [A]}, {'clients': [B]}]), \
             patch('runtime.VoiceRuntime.focused_monitor', return_value='screen'):
            root = Path(directory)
            app = VoiceRuntime(root, root / 'status.json')
            app.type_command()
            first = app.state['written_entry']
            self.assertEqual(first['counts'], {})
            self.assertTrue(first['suggestions'])
            self.assertIn('omarchy voice manager', first['dynamic_suggestions'][0]['text'])
            app.cancel()
            app.type_command()
            second = app.state['written_entry']
            self.assertIn('another project', second['dynamic_suggestions'][0]['text'])
            self.assertFalse(any('omarchy voice manager' in r['text'] for r in second['dynamic_suggestions']))
            with app.command_store.connect() as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM commands').fetchone()[0], 0)

    def test_live_refresh_removes_closed_terminal_and_its_history_but_keeps_draft_context(self):
        with tempfile.TemporaryDirectory() as directory, patch('runtime.VoiceRuntime.focused_monitor', return_value='screen'):
            root = Path(directory)
            app = VoiceRuntime(root, root / 'status.json')
            old = terminal_suggestions({'clients': [A]})[0]
            app.command_store.record(old['text'], old['command'], 'written')
            with patch('runtime.capture_window_context', return_value={'active': A, 'clients': [A]}):
                app.type_command()
            token = app.pending_written['token']
            self.assertEqual(app.state['written_entry']['counts'].get(old['command']), 1)
            app.apply_written_refresh(token, {'active': B, 'clients': [B]}, terminal_suggestions({'clients': [B]}))
            entry = app.state['written_entry']
            self.assertFalse(any('omarchy voice manager' in row['text'] for row in entry['dynamic_suggestions']))
            self.assertEqual(app.pending_written['context']['active'], A)
            self.assertEqual(app.pending_written['context']['clients'], [B])
            self.assertIn(old['text'], app.command_store.recent())
            # A late refresh must not change a submitted command's targets.
            app.busy = True
            app.apply_written_refresh(token, {'clients': []}, [])
            self.assertEqual(app.pending_written['context']['clients'], [B])

    def test_shell_path_label_omits_hostname_and_distinguishes_task_terminal(self):
        shell = dict(A, title='alex@workstation:~/Projects/voice-manager')
        task = dict(B, title='Fix layout | voice-manager')
        context = {'clients': [shell, task]}
        rows = terminal_suggestions(context)
        shell_close = next(row for row in rows if row['text'] == 'close the shell alex projects voice manager')
        self.assertFalse(any('workstation' in form for row in rows for form in row['forms']))
        with tempfile.TemporaryDirectory() as directory:
            result = IntentMatcher(Path(directory)/'aliases.json').parse(shell_close['text'], inject_windows(context).expansions)
            self.assertEqual(result.command, shell_close['command'])
        other_host = dict(shell, title='alex@otherhost:/home/alex/Projects/voice-manager')
        self.assertEqual(terminal_suggestions({'clients':[other_host]})[0]['text'], shell_close['text'])
