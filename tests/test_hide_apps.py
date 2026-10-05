from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from intent_matching import IntentMatcher
from window_resolution import WindowResolution
from runtime import VoiceRuntime
from command_catalog import APPS

CHROME = dict(address='0x1', pid=1, stableId='one', workspace={'id': 2}, **{'class':'chromium'})
FIREFOX = dict(CHROME, address='0x2', pid=2, stableId='two', **{'class':'firefox'})
X = dict(CHROME, address='0x3', pid=3, stableId='three', **{'class':next(iter(APPS['x']['classes']))})


class HideAppTests(unittest.TestCase):
    def test_app_filter_and_canonical_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            matcher = IntentMatcher(Path(directory)/'aliases.json')
            for phrase, app, expected in [('hide chrome','chrome',CHROME), ('hide X','x',X), ('hide twitter','x',X)]:
                result = matcher.parse(phrase)
                self.assertEqual(result.canonical_plan, [{'intent':'window.hide','arguments':{'target':{'kind':'application','value':app}}}])
                resolution = WindowResolution(result.intent, {'clients':[CHROME,FIREFOX,X]})
                self.assertIsNone(resolution.advance())
                self.assertEqual(resolution.resolved['window'],expected)
            self.assertIsNone(matcher.parse('do not hide chrome').command)
            self.assertNotEqual(matcher.parse('hide chorme').command,'hide:chrome')
            with self.assertRaisesRegex(RuntimeError,'No open window'):
                WindowResolution(matcher.parse('hide chrome').intent, {'clients':[FIREFOX]}).advance()

    def test_ambiguous_browser_prompts_then_hides_selected_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            matcher = IntentMatcher(root/'aliases.json')
            resolution = WindowResolution(matcher.parse('hide chrome').intent,
                {'clients':[CHROME,dict(CHROME,address='0x4',pid=4,stableId='four')]})
            self.assertEqual(len(resolution.advance().candidates),2)
            resolution.choose(resolution.advance(),0)
            app = VoiceRuntime(root,root/'status.json')
            with patch('runtime.threading.Thread') as thread:
                app.resolve_windows(resolution)
            self.assertEqual(thread.call_args.kwargs['target'],app.run_hide_selection)
            with patch('runtime.hide_current_window',return_value='Hidden') as hide, \
                 patch('runtime.GLib.idle_add',side_effect=lambda fn,*args:fn(*args)):
                app.run_hide_selection(resolution)
            hide.assert_called_once_with({'active':CHROME})
            self.assertEqual(app.state['state'],'Ready')
