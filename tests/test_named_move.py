import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from intent_matching import IntentMatcher
from os_actions import move_app_other_screen
from runtime import VoiceRuntime
from window_vocabulary import inject_windows


def client(address, title, app='foot', recent=0):
    return dict(address=address, title=title, pid=10, stableId=address,
                monitor=0, mapped=True, focusHistoryID=recent, **{'class': app})


class NamedMoveTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.data = Path(directory.name)
        self.matcher = IntentMatcher(self.data / 'aliases.json')
        self.explain = client('0x1', 'Explain Omarchy plugins | Projects')
        self.patch = client('0x2', 'Patch monitor replug bug | Projects')
        self.chrome = client('0x3', 'Chrome', 'chromium')
        self.context = {'active': self.chrome, 'clients': [self.explain, self.patch, self.chrome]}
        self.windows = inject_windows(self.context)

    def test_terminal_names_articles_suffixes_and_fuzzy_spelling(self):
        for name, address in [('explain terminal', '0x1'), ('patch monitor terminal', '0x2'),
                              ('explan terminal', '0x1')]:
            for article in ('', 'the '):
                for suffix in ('other screen', 'the other screen', 'other monitor', 'the other monitor'):
                    phrase = f'move {article}{name} to {suffix}'
                    with self.subTest(phrase=phrase):
                        result = self.matcher.parse(phrase, self.windows.expansions)
                        self.assertEqual(result.intent.type, 'move_named_window')
                        args = dict(result.intent.arguments)
                        self.assertEqual(args['monitor'], 'other')
                        self.assertEqual(self.windows.targets[args['window']]['address'], address)

    def test_apps_share_patterns_and_fuzzy_matching(self):
        for name, app in [('chrome', 'browser'), ('chromium', 'browser'), ('google chrome', 'browser'),
                          ('twitter', 'x'), ('x', 'x'), ('discord', 'discord'), ('chorme', 'browser')]:
            result = self.matcher.parse(f'move {name} to the other screen', self.windows.expansions)
            self.assertEqual(dict(result.intent.arguments),
                             {'application': app, 'selection': 'most_recent', 'monitor': 'other'})

    def test_unknown_names_never_move_current_window(self):
        for expansions in (self.windows.expansions, ()):
            for name in ('nonexistent terminal', 'nonexistent', 'unrelated app'):
                for screen in ('screen', 'screan'):
                    result = self.matcher.parse(f'move {name} to the other {screen}', expansions)
                    self.assertIsNone(result.command)

    def test_duplicate_prefix_and_app_collision_are_ambiguous(self):
        for extra, name in [(client('0x4', 'Explain audio | other'), 'explain terminal'),
                            (client('0x4', 'Chrome'), 'chrome')]:
            windows = inject_windows({'clients': self.context['clients'] + [extra]})
            result = self.matcher.parse(f'move {name} to the other screen', windows.expansions)
            self.assertEqual(result.status, 'ambiguous')

    def test_runtime_moves_named_capture_without_learning_or_closing(self):
        app = VoiceRuntime(self.data, self.data / 'status.json')
        app.model = object()
        with patch('runtime.save_transcript', return_value=('move the explan terminal to the other screen', {})), \
             patch('runtime.move_other_screen', return_value='Moved') as move, \
             patch('runtime.GLib.idle_add', side_effect=lambda fn, *args: fn(*args)), \
             patch.object(app, 'execute') as execute:
            app.transcribe(self.data / 'test.wav', self.context, True)
        self.assertEqual(move.call_args.args[0]['address'], self.explain['address'])
        execute.assert_not_called()
        self.assertFalse(self.matcher.path.exists())
        self.assertEqual(app.state['state'], 'Ready')

    def test_app_selection_uses_capture_and_does_not_launch_missing_app(self):
        for name, app_class in [('browser', 'chromium'), ('x', 'chrome-x.com__-Default'), ('discord', 'discord')]:
            target = client('0x4', 'App', app_class)
            older = client('0x5', 'App', app_class, recent=5)
            context = {'active': self.explain, 'clients': [older, target, self.explain]}
            with patch('os_actions.move_other_screen', return_value='Moved') as move:
                VoiceRuntime.execute('move-app:' + name, context)
                move.assert_called_once_with(target)
        with patch('os_actions.run') as run:
            with self.assertRaisesRegex(RuntimeError, 'No open window'):
                move_app_other_screen('x', self.context)
            run.assert_not_called()

    def test_replaced_captured_app_is_rejected(self):
        replacement = dict(self.chrome, stableId='replacement')
        with patch('os_actions.run', return_value=json.dumps([replacement])) as run:
            with self.assertRaisesRegex(RuntimeError, 'changed'):
                move_app_other_screen('browser', self.context)
            run.assert_called_once_with(['hyprctl', 'clients', '-j'])
