"""Live grammar injection, ambiguous names, and captured-window identity."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from grammar_engine import compile_grammar
from command_catalog import WINDOW_RULES
from intent_matching import IntentMatcher
from os_actions import focus_named_window
from runtime import VoiceRuntime
from window_vocabulary import inject_windows, window_names


def terminal(stable='a', title='⠋ Define intent grammars | skipper', address='0x1', pid=10):
    return dict(stableId=stable, title=title, address=address, pid=pid, mapped=True,
                **{'class': 'foot'}, workspace={'name': '2'})


class WindowVocabularyTests(unittest.TestCase):
    def test_focus_on_uses_live_names_and_rejects_duplicate_vim_terminals(self):
        windows = inject_windows({'clients': [terminal(title='Vim | project')]})
        for phrase in ('focus on vim terminal', 'focus on the vim terminal'):
            result = IntentMatcher(Path('/nonexistent/skipper-test-aliases.json')).parse(phrase, windows.expansions)
            self.assertEqual(result.intent.type, 'focus_window')
            self.assertEqual(windows.targets[dict(result.intent.arguments)['window']]['stableId'], 'a')
        duplicate = inject_windows({'clients': [terminal(title='Vim | project'),
                                               terminal('b', 'Vim | other', '0x2', 20)]})
        result = IntentMatcher(Path('/nonexistent/skipper-test-aliases.json')).parse('focus on the vim terminal', duplicate.expansions)
        self.assertEqual(result.status, 'ambiguous')

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.data = Path(directory.name)
        self.matcher = IntentMatcher(self.data / 'aliases.json')
        self.context = {'clients': [terminal(), terminal('b', '[ ! ] Action Required | Patch monitor replug bug | Projects', '0x2', 20)]}
        self.windows = inject_windows(self.context)

    def test_shared_patterns_use_all_live_names_and_fuzzy_variants(self):
        for text, expected in [('focus skipper', 'skipper'), ('switch to the skipper terminal', 'skipper'),
                               ('go to patch monitor replug bug', 'Projects'), ('focuss skipper', 'skipper'),
                               ('focus the skipper codex', 'skipper'), ('focus the monitor replug bug', 'Projects')]:
            with self.subTest(text=text):
                result = self.matcher.parse(text, self.windows.expansions)
                self.assertEqual(result.status, 'matched')
                self.assertEqual(result.intent.type, 'focus_window')
                key = dict(result.intent.arguments)['window']
                self.assertTrue(self.windows.targets[key]['voice_label'].endswith(expected))
                self.assertTrue(result.selected.to_dict()['expansions'])
        self.assertFalse(self.matcher.path.exists())

    def test_changing_titles_updates_names_without_changing_identity(self):
        changed = inject_windows({'clients': [terminal(title='[ ! ] Action Required | Other task | skipper')]})
        self.assertEqual(self.windows.words[0].id, changed.words[0].id)
        self.assertNotEqual(self.windows.revision, changed.revision)
        self.assertNotIn('define intent grammars', changed.words[0].forms)
        self.assertIn('other task', changed.words[0].forms)
        self.assertIn('skipper', changed.words[0].forms)
        self.assertNotIn('action required', changed.words[0].forms)

    def test_duplicate_project_names_remain_ambiguous_even_on_exact_match(self):
        windows = inject_windows({'clients': [terminal(), terminal('b', 'Fix audio | skipper', '0x2', 20)]})
        for text in ('focus skipper', 'focus skipper terminal', 'focus skipp'):
            result = self.matcher.parse(text, windows.expansions)
            self.assertEqual(result.status, 'ambiguous')
            self.assertIsNone(result.command)
        self.assertEqual(self.matcher.parse('focus fix audio', windows.expansions).status, 'matched')

    def test_new_pattern_covers_live_entries_without_specific_phrase_edits(self):
        from dataclasses import replace
        rule = replace(WINDOW_RULES[0], patterns=('find <window>',))
        expansions = compile_grammar((rule,), {'window': self.windows.words},
                                     {'focus_window': {'window': tuple(self.windows.targets)}}, allow_ambiguous=True)
        for word in self.windows.words:
            result = self.matcher.parse('find ' + word.forms[0], expansions)
            self.assertEqual(dict(result.intent.arguments)['window'], word.id)

    def test_static_commands_and_unknown_names(self):
        self.assertEqual(self.matcher.parse('open gmail', self.windows.expansions).command, 'site:gmail')
        for text in ('focus unknown terminal', 'focus the nowhere window', "don't focus skipper"):
            result = self.matcher.parse(text, self.windows.expansions)
            self.assertIsNone(result.command, (text, result))
        self.assertFalse(inject_windows(None).expansions)
        self.assertFalse(inject_windows({'clients': [terminal(stable='')]}).words)
        self.assertFalse(inject_windows({'clients': [terminal(address='0x1;bad')]}).words)

    def test_static_and_dynamic_phrase_collision_is_not_overwritten(self):
        windows = inject_windows({'clients': [terminal(title='Chrome')]})
        result = self.matcher.parse('focus chrome', windows.expansions)
        self.assertEqual(result.status, 'ambiguous')
        self.assertEqual({c.intent.type for c in result.candidates}, {'open_application', 'focus_window'})

    def test_target_revalidated_before_focus_and_title_changes_are_allowed(self):
        target = self.windows.targets[self.windows.words[0].id]
        changed_title = terminal(title='Different status and title')
        with patch('os_actions.run', return_value=json.dumps([changed_title])) as run, patch('os_actions.focus') as focus:
            focus_named_window(target)
            self.assertEqual(run.call_args_list[1].args[0], ['hyprctl', 'dispatch',
                f'hl.dsp.window.alter_zorder({{ mode = "top", window = "address:{target["address"]}" }})'])
            focus.assert_called_once_with(changed_title)
        for clients in ([], [terminal(stable='replacement')], [terminal(pid=999)]):
            with patch('os_actions.run', return_value=json.dumps(clients)), patch('os_actions.focus') as focus:
                with self.assertRaises(RuntimeError):
                    focus_named_window(target)
                focus.assert_not_called()

    def test_runtime_uses_capture_and_never_learns_ephemeral_window_aliases(self):
        app = VoiceRuntime(self.data, self.data / 'status.json')
        app.model = object()
        with patch('runtime.save_transcript', return_value=('focus skipp', {})), \
             patch('runtime.focus_named_window', return_value='Focused Skipper') as focus, \
             patch('runtime.GLib.idle_add', side_effect=lambda fn,*args: fn(*args)), \
             patch.object(app, 'execute') as execute:
            app.transcribe(self.data / 'test.wav', self.context, True)
        self.assertEqual(focus.call_args.args[0]['stableId'], 'a')
        execute.assert_not_called()
        self.assertFalse((self.data / 'aliases.json').exists())
        self.assertEqual(app.state['intent']['type'], 'focus_window')
        self.assertEqual(app.state['state'], 'Ready')

    def test_plain_terminal_path_is_a_spoken_name(self):
        _, forms = window_names('greg@machine: ~/Projects/skipper')
        self.assertIn('skipper terminal', forms)

    def test_close_uses_same_names_including_shortened_title(self):
        for phrase in ('close the patch monitor terminal', 'close patch monitor replug bug',
                       'close projects', 'close the projects codex'):
            result = self.matcher.parse(phrase, self.windows.expansions)
            self.assertEqual(result.intent.type, 'close_named_window')
            key = dict(result.intent.arguments)['window']
            self.assertEqual(self.windows.targets[key]['stableId'], 'b')

    def test_unknown_or_duplicate_close_names_do_not_fall_back_to_recent_terminal(self):
        for expansions in (self.windows.expansions, ()):
            result = self.matcher.parse('close the nonexistent terminal', expansions)
            self.assertIsNone(result.command)
        windows = inject_windows({'clients': [terminal(), terminal('b', 'Fix audio | skipper', '0x2', 20)]})
        result = self.matcher.parse('close the skipper terminal', windows.expansions)
        self.assertEqual(result.status, 'ambiguous')
        self.assertIsNone(result.command)
        self.assertEqual(self.matcher.parse('close terminal', windows.expansions).command, 'close:terminal')

    def test_named_close_confirmation_preserves_target_and_never_learns(self):
        app = VoiceRuntime(self.data, self.data / 'status.json')
        app.model = object()
        with patch('runtime.save_transcript', return_value=('close the patch monitor terminal', {})), \
             patch('runtime.terminal_has_jobs', return_value=True), \
             patch('runtime.terminal_close_target') as recent, \
             patch('runtime.close_terminal') as close, \
             patch('runtime.GLib.idle_add', side_effect=lambda fn,*args: fn(*args)):
            app.transcribe(self.data / 'test.wav', self.context, True)
            self.assertEqual(app.state['state'], 'Confirm')
            pending = app.pending
            self.assertEqual(pending[2]['stableId'], 'b')
            self.assertFalse(pending[4])
            close.assert_not_called()
            recent.assert_not_called()
            with patch('runtime.threading.Thread'):
                app.confirm(pending[0])
            close.return_value = 'Closed selected terminal'
            app.run_confirmed(pending)
            close.assert_called_once_with(pending[2])
        self.assertFalse((self.data / 'aliases.json').exists())

    def test_named_close_idle_and_disabled_warning_use_captured_target(self):
        from settings import Settings
        for confirm, jobs in ((True, False), (False, True)):
            Settings(self.data / 'settings.json').set_confirm_terminal_close(confirm)
            app = VoiceRuntime(self.data, self.data / 'status.json')
            app.model = object()
            with patch('runtime.save_transcript', return_value=('close the patch monitor terminal', {})), \
                 patch('runtime.terminal_has_jobs', return_value=jobs), \
                 patch('runtime.close_terminal', return_value='Closed') as close, \
                 patch('runtime.GLib.idle_add', side_effect=lambda fn,*args: fn(*args)):
                app.transcribe(self.data / 'test.wav', self.context, True)
                self.assertEqual(close.call_args.args[0]['stableId'], 'b')
                self.assertIsNone(app.pending)
                self.assertEqual(app.state['state'], 'Ready')
            self.assertFalse((self.data / 'aliases.json').exists())

    def test_replaced_named_target_is_rejected_after_approval(self):
        app = VoiceRuntime(self.data, self.data / 'status.json')
        target = self.windows.targets[self.windows.words[1].id]
        pending = ('token', 'close-window:' + self.windows.words[1].id, target, 'close projects', False)
        replacement = terminal('replacement', 'Same title', '0x2', 20)
        with patch('os_actions.run', return_value=json.dumps([replacement])) as run, \
             patch('runtime.GLib.idle_add', side_effect=lambda fn,*args: fn(*args)):
            app.run_confirmed(pending)
        run.assert_called_once_with(['hyprctl', 'clients', '-j'])
        self.assertEqual(app.state['state'], 'Error')
