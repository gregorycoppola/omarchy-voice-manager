"""App close phrases select exact app classes, not similarly named web pages."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from intent_matching import IntentMatcher
from os_actions import execute_command, parse_command


class CloseAppPhraseTests(unittest.TestCase):
    def test_full_phrases_are_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            matcher = IntentMatcher(Path(directory) / 'aliases.json')
            for app, names in [('x', ('x', 'twitter')),
                               ('files', ('file browser', 'file manager', 'files', 'nautilus'))]:
                for name in names:
                    for phrase in (f'close {name}', f'close the {name}',
                                   f'close {name} window', f'close the {name} window'):
                        result = matcher.parse(phrase)
                        self.assertEqual(result.method, 'exact', phrase)
                        self.assertEqual(result.command, f'close:{app}', phrase)
                        self.assertEqual(parse_command(phrase), f'close:{app}')
                        self.assertEqual(dict(result.intent.arguments)['application'], app)
            self.assertIsNone(matcher.parse('do not close the file browser window').command)

    def test_files_closes_only_most_recent_nautilus(self):
        clients = [dict(address='0x1', **{'class': 'chromium'}, title='Files', focusHistoryID=0),
                   dict(address='0x2', **{'class': 'org.gnome.Nautilus'}, focusHistoryID=5),
                   dict(address='0x3', **{'class': 'org.gnome.Nautilus'}, focusHistoryID=1)]
        with patch('os_actions.run', side_effect=[json.dumps(clients), 'ok', json.dumps(clients[:2])]) as run:
            self.assertEqual(execute_command('close:files'), 'Closed Files window')
        dispatch = run.call_args_list[1].args[0][-1]
        self.assertIn('address:0x3', dispatch)
        self.assertIn('window.close', dispatch)

    def test_missing_files_does_not_close_browser(self):
        with patch('os_actions.run', return_value=json.dumps([
                dict(address='0x1', title='File browser', **{'class': 'chromium'})])) as run:
            self.assertEqual(execute_command('close:files'), 'No open Files window')
            run.assert_called_once()

    def test_browser_phrase_and_picker_close_only_chosen_identity(self):
        from runtime import VoiceRuntime
        from os_actions import close_selected_window
        browser = dict(address='0x1', pid=1, stableId='one', mapped=True, title='First',
                       workspace={'id': 1}, **{'class': 'chromium'})
        second = dict(browser, address='0x2', pid=2, stableId='two', title='Second')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = VoiceRuntime(root, root / 'status.json')
            with patch('runtime.GLib.idle_add', side_effect=lambda fn, *args: fn(*args)), \
                 patch('runtime.close_selected_window', return_value='Closed the selected window') as close:
                app.interpret('close the browser', {'active': browser, 'clients': [browser, second]})
                self.assertEqual(app.state['state'], 'Choose')
                self.assertEqual(app.state['clarification']['prompt'], 'Which browser window do you mean?')
                close.assert_not_called()
                token = app.state['clarification']['choices'][1]['token']
                with patch('runtime.threading.Thread') as worker:
                    app.choose_window('old-token')
                    worker.assert_not_called()
                    app.choose_window(token)
                worker.call_args.kwargs['target'](*worker.call_args.kwargs['args'])
                close.assert_called_once_with(second)
        with patch('os_actions.run', side_effect=[json.dumps([browser, second]), 'ok', json.dumps([browser])]) as run:
            self.assertEqual(close_selected_window(second), 'Closed the selected window')
            self.assertIn('address:0x2', run.call_args_list[1].args[0][-1])
        with patch('os_actions.run', return_value=json.dumps([dict(second, pid=99)])) as run:
            with self.assertRaisesRegex(RuntimeError, 'closed or changed'):
                close_selected_window(second)
            run.assert_called_once()

    def test_all_app_closes_resolve_unique_or_ask(self):
        from window_resolution import WindowResolution
        with tempfile.TemporaryDirectory() as directory:
            matcher = IntentMatcher(Path(directory) / 'aliases.json')
            for phrase, cls in [('close the browser', 'chromium'),
                                ('close the x window', 'chrome-x.com__-Default'),
                                ('close the file browser window', 'org.gnome.Nautilus')]:
                result = matcher.parse(phrase)
                self.assertEqual(result.method, 'exact')
                self.assertEqual(dict(result.intent.arguments)['selection'], 'unique_or_choose')
                first = dict(address='0x1', pid=1, stableId='one', **{'class': cls})
                second = dict(first, address='0x2', pid=2, stableId='two')
                one = WindowResolution(result.intent, {'clients': [first]})
                self.assertIsNone(one.advance())
                self.assertEqual(one.resolved['window'], first)
                two = WindowResolution(result.intent, {'clients': [first, second]})
                self.assertEqual(len(two.advance().candidates), 2)
                with self.assertRaisesRegex(RuntimeError, 'No open window'):
                    WindowResolution(result.intent, {'clients': []}).advance()
