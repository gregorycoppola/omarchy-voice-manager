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


def terminal(stable='a', title='⠋ Define intent grammars | keety', address='0x1', pid=10):
    return dict(stableId=stable, title=title, address=address, pid=pid, mapped=True,
                **{'class': 'foot'}, workspace={'name': '2'})


class WindowVocabularyTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.data = Path(directory.name)
        self.matcher = IntentMatcher(self.data / 'aliases.json')
        self.context = {'clients': [terminal(), terminal('b', '[ ! ] Action Required | Patch monitor replug bug | Projects', '0x2', 20)]}
        self.windows = inject_windows(self.context)

    def test_shared_patterns_use_all_live_names_and_fuzzy_variants(self):
        for text, expected in [('focus keety', 'keety'), ('switch to the keety terminal', 'keety'),
                               ('go to patch monitor replug bug', 'Projects'), ('focuss keety', 'keety'),
                               ('focus the keety codex', 'keety'), ('focus the monitor replug bug', 'Projects')]:
            with self.subTest(text=text):
                result = self.matcher.parse(text, self.windows.expansions)
                self.assertEqual(result.status, 'matched')
                self.assertEqual(result.intent.type, 'focus_window')
                key = dict(result.intent.arguments)['window']
                self.assertTrue(self.windows.targets[key]['voice_label'].endswith(expected))
                self.assertTrue(result.selected.to_dict()['expansions'])
        self.assertFalse(self.matcher.path.exists())

    def test_changing_titles_updates_names_without_changing_identity(self):
        changed = inject_windows({'clients': [terminal(title='[ ! ] Action Required | Other task | keety')]})
        self.assertEqual(self.windows.words[0].id, changed.words[0].id)
        self.assertNotEqual(self.windows.revision, changed.revision)
        self.assertNotIn('define intent grammars', changed.words[0].forms)
        self.assertIn('other task', changed.words[0].forms)
        self.assertIn('keety', changed.words[0].forms)
        self.assertNotIn('action required', changed.words[0].forms)

    def test_duplicate_project_names_remain_ambiguous_even_on_exact_match(self):
        windows = inject_windows({'clients': [terminal(), terminal('b', 'Fix audio | keety', '0x2', 20)]})
        for text in ('focus keety', 'focus keety terminal', 'focus keet'):
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
        for text in ('focus unknown terminal', 'focus the nowhere window', "don't focus keety"):
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
        with patch('os_actions.run', return_value=json.dumps([changed_title])), patch('os_actions.focus') as focus:
            focus_named_window(target)
            focus.assert_called_once_with(changed_title)
        for clients in ([], [terminal(stable='replacement')], [terminal(pid=999)]):
            with patch('os_actions.run', return_value=json.dumps(clients)), patch('os_actions.focus') as focus:
                with self.assertRaises(RuntimeError):
                    focus_named_window(target)
                focus.assert_not_called()

    def test_runtime_uses_capture_and_never_learns_ephemeral_window_aliases(self):
        app = VoiceRuntime(self.data, self.data / 'status.json')
        app.model = object()
        with patch('runtime.save_transcript', return_value=('focus keet', {})), \
             patch('runtime.focus_named_window', return_value='Focused Keety') as focus, \
             patch('runtime.GLib.idle_add', side_effect=lambda fn,*args: fn(*args)), \
             patch.object(app, 'execute') as execute:
            app.transcribe(self.data / 'test.wav', self.context, True)
        self.assertEqual(focus.call_args.args[0]['stableId'], 'a')
        execute.assert_not_called()
        self.assertFalse((self.data / 'aliases.json').exists())
        self.assertEqual(app.state['intent']['type'], 'focus_window')
        self.assertEqual(app.state['state'], 'Ready')

    def test_plain_terminal_path_is_a_spoken_name(self):
        _, forms = window_names('greg@machine: ~/Projects/keety')
        self.assertIn('keety terminal', forms)
