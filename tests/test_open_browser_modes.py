"""Browser launch modes retain the original window and resolve ambiguity."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from intent_matching import IntentMatcher
from os_actions import prepare_browser_context, fullscreen_selected_browser
from runtime import VoiceRuntime
from window_resolution import WindowResolution

TERM = dict(address='0x1', pid=1, stableId='one', workspace={'id': 1}, monitor=0,
            mapped=True, **{'class': 'foot'})
BROWSER = dict(TERM, address='0x2', pid=2, stableId='two', **{'class': 'chromium'})
OTHER = dict(BROWSER, address='0x3', pid=3, stableId='three')


class BrowserModeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.data = Path(temp.name)
        self.matcher = IntentMatcher(self.data / 'aliases.json')

    def test_phrases_have_distinct_modes_and_fullscreen_default(self):
        for phrase in ('open the browser and tile', 'open browser and tile', 'open chrome and tile it'):
            parsed = self.matcher.parse(phrase)
            self.assertEqual(parsed.method, 'exact')
            self.assertEqual(parsed.intent.type, 'open_browser_and_tile')
        default = self.matcher.parse('open the browser').intent
        self.assertEqual(default.type, 'open_browser_fullscreen')
        for phrase in ('open the browser in full screen', 'open browser fullscreen', 'open chromium in fullscreen'):
            self.assertEqual(self.matcher.parse(phrase).intent, default)
        self.assertIsNone(self.matcher.parse('do not open the browser and tile').intent)

    def test_reuses_browser_without_launch_or_changing_capture(self):
        context = {'active': TERM, 'clients': [TERM, BROWSER, OTHER]}
        with patch('os_actions.run', return_value=json.dumps(context['clients'])), \
             patch('os_actions.launch_desktop') as launch:
            prepared = prepare_browser_context(context, require_focused=True)
        launch.assert_not_called()
        resolution = WindowResolution(self.matcher.parse('open the browser and tile').intent, prepared)
        self.assertEqual(resolution.advance().prompt, 'Which browser window do you mean?')
        self.assertEqual(resolution.resolved['first'], TERM)
        self.assertEqual(prepared, context)
        self.assertIsNot(prepared, context)

    def test_launch_preserves_terminal_as_first_even_after_focus_changes(self):
        context = {'active': deepcopy(TERM), 'clients': [deepcopy(TERM)]}
        launcher = Mock()
        launcher.poll.return_value = None
        with patch('os_actions.run', side_effect=[json.dumps([TERM]), json.dumps([TERM]), json.dumps([TERM, BROWSER])]), \
             patch('os_actions.Path.is_file', return_value=True), \
             patch('os_actions.launch_desktop', return_value=launcher) as launch, \
             patch('os_actions.time.sleep'):
            prepared = prepare_browser_context(context, require_focused=True)
        launch.assert_called_once()
        self.assertEqual(launch.call_args.args[0].name, 'chromium.desktop')
        self.assertEqual(prepared['active'], TERM)
        self.assertEqual(context['clients'], [TERM])
        r = WindowResolution(self.matcher.parse('open the browser and tile').intent, prepared)
        self.assertIsNone(r.advance())
        self.assertEqual([r.resolved[k] for k in ('first', 'second')], [TERM, BROWSER])

    def test_missing_or_stale_original_never_launches(self):
        with patch('os_actions.run', return_value='[]'), patch('os_actions.launch_desktop') as launch:
            for context in ({}, {'active': TERM, 'clients': [TERM]}):
                with self.assertRaises(RuntimeError):
                    prepare_browser_context(context, require_focused=True)
            launch.assert_not_called()

    def test_launch_failure_and_timeout_are_reported(self):
        for poll, times, error in [(1, [0, 0], 'launcher failed'), (None, [0, 11], 'no browser window')]:
            with patch('os_actions.Path.is_file', return_value=True), \
                 patch('os_actions.launch_desktop', return_value=Mock(poll=Mock(return_value=poll))), \
                 patch('os_actions.run', return_value='[]'), \
                 patch('os_actions.time.monotonic', side_effect=times):
                with self.assertRaisesRegex(RuntimeError, error):
                    prepare_browser_context({'active': TERM, 'clients': []})

    def test_fullscreen_is_not_maximize_and_checks_identity(self):
        remote = dict(BROWSER, workspace={'id': 2})
        final = dict(BROWSER, fullscreen=2, fullscreenClient=2)
        with patch('os_actions.run', side_effect=[json.dumps([remote]), 'ok', 'ok', json.dumps(final)]) as run, \
             patch('os_actions.focus') as focus:
            self.assertEqual(fullscreen_selected_browser({'active': TERM}, remote), 'Opened the browser in full screen')
        commands = [c.args[0][-1] for c in run.call_args_list if 'dispatch' in c.args[0]]
        self.assertIn('workspace = "1"', commands[0])
        self.assertIn('internal = 2, client = 2', commands[1])
        focus.assert_called_once_with(remote)
        with patch('os_actions.run', return_value=json.dumps([dict(BROWSER, pid=99)])) as run:
            with self.assertRaisesRegex(RuntimeError, 'closed or changed'):
                fullscreen_selected_browser({'active': TERM}, BROWSER)
            run.assert_called_once()

    def test_runtime_uses_original_context_for_each_mode(self):
        for phrase, action, expected in [
                ('open the browser and tile', 'tile_selected_windows', [TERM, BROWSER]),
                ('open the browser in full screen', 'fullscreen_selected_browser', BROWSER)]:
            app = VoiceRuntime(self.data, self.data / 'status.json')
            context = {'active': TERM, 'clients': [TERM, BROWSER]}
            with patch('runtime.prepare_browser_context', return_value=context) as prepare, \
                 patch('runtime.GLib.idle_add', side_effect=lambda fn, *args: fn(*args)), \
                 patch('runtime.threading.Thread') as worker:
                app.interpret(phrase, context)
            prepare.assert_called_once_with(context, require_focused='and tile' in phrase)
            with patch('runtime.' + action, return_value='Done') as execute, \
                 patch('runtime.GLib.idle_add', side_effect=lambda fn, *args: fn(*args)):
                worker.call_args.kwargs['target'](*worker.call_args.kwargs['args'])
            execute.assert_called_once_with(context, expected)
            self.assertEqual(app.state['state'], 'Ready')

    def test_browser_typos_keep_the_explicit_layout(self):
        for typo in ('brwoser', 'brwoswer', 'brower', 'browesr'):
            for ending, expected in [(' and tile', 'open_browser_and_tile'),
                                     (' in full screen', 'open_browser_fullscreen'),
                                     ('', 'open_browser_fullscreen')]:
                result = self.matcher.parse(f'open the {typo}{ending}')
                self.assertEqual(result.intent.type, expected)
                self.assertEqual(result.method, 'fuzzy')
            self.assertIsNone(self.matcher.parse(f'do not open the {typo} and tile').intent)
        self.assertIsNone(self.matcher.parse('open the brwoser and delete').intent)

    def test_missing_chromium_does_not_launch_a_different_browser(self):
        with patch('os_actions.Path.is_file', return_value=False), \
             patch('os_actions.launch_desktop') as launch:
            with self.assertRaisesRegex(RuntimeError, 'Chromium, is not installed'):
                prepare_browser_context({'active': TERM, 'clients': []})
            launch.assert_not_called()
