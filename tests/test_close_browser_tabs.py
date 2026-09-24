import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from intent_matching import IntentMatcher
from os_actions import close_browser_tabs
from runtime import VoiceRuntime
from window_resolution import WindowResolution

TARGET = dict(address='0x1', pid=1, stableId='one', mapped=True, visible=True,
              workspace={'id': 1}, **{'class': 'chromium'})


class CloseBrowserTabsTests(unittest.TestCase):
    def test_phrases_route_through_picker_and_leave_close_window_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            matcher = IntentMatcher(root / 'aliases.json')
            for text in ('close all tabs', 'close all browser tabs',
                         'close all tabs in the browser', 'close all tabs on the browser'):
                result = matcher.parse(text)
                self.assertEqual(result.method, 'exact')
                self.assertEqual(result.intent.type, 'close_browser_tabs')
                other = dict(TARGET, address='0x2', pid=2, stableId='two')
                resolution = WindowResolution(result.intent, {'clients': [TARGET, other]})
                self.assertEqual(len(resolution.advance().candidates), 2)
            self.assertEqual(matcher.parse('close the browser').intent.type, 'close_window')
            self.assertIsNone(matcher.parse('do not close all tabs').command)
            self.assertNotEqual(matcher.parse('close all abs').command, 'browser:close_tabs')
            resolution = WindowResolution(matcher.parse('close all tabs').intent, {'clients': [TARGET]})
            app = VoiceRuntime(root, root / 'status.json')
            with patch('runtime.threading.Thread') as thread:
                app.resolve_windows(resolution)
            self.assertEqual(thread.call_args.kwargs['target'], app.run_close_browser_tabs)
            with patch('runtime.close_browser_tabs', return_value='One blank tab remains') as reset, \
                 patch('runtime.GLib.idle_add', side_effect=lambda fn,*args:fn(*args)):
                app.run_close_browser_tabs(resolution)
                reset.assert_called_once_with(TARGET)
                self.assertEqual(app.state['state'], 'Ready')

    def test_native_identity_and_focus_checked_before_mutation(self):
        def reset(focus_target, verify_target):
            focus_target()
            verify_target()
            return {'closed': 3}
        with patch('os_actions.connection.reset_tabs', side_effect=reset), \
             patch('os_actions.focus') as focus, \
             patch('os_actions.run', side_effect=[json.dumps([TARGET]), json.dumps(TARGET), json.dumps(TARGET)]):
            self.assertIn('one blank tab', close_browser_tabs(TARGET))
            focus.assert_called_once_with(TARGET)
        changed = dict(TARGET, stableId='changed')
        with patch('os_actions.connection.reset_tabs', side_effect=reset), \
             patch('os_actions.focus') as focus, \
             patch('os_actions.run', return_value=json.dumps([changed])):
            with self.assertRaisesRegex(RuntimeError, 'closed or changed'):
                close_browser_tabs(TARGET)
            focus.assert_not_called()
        with patch('os_actions.connection.reset_tabs', side_effect=reset), \
             patch('os_actions.focus'), \
             patch('os_actions.run', side_effect=[json.dumps([TARGET]), json.dumps(TARGET), json.dumps(changed)]):
            with self.assertRaisesRegex(RuntimeError, 'lost focus'):
                close_browser_tabs(TARGET)

    def test_unsupported_browser_never_connects(self):
        with patch('os_actions.connection.reset_tabs') as reset:
            with self.assertRaisesRegex(RuntimeError, 'Chrome/Chromium'):
                close_browser_tabs(dict(TARGET, **{'class': 'firefox'}))
            reset.assert_not_called()
