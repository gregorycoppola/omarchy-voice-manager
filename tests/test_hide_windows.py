import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from intent_matching import IntentMatcher
from os_actions import capture_window_context, hide_windows
from runtime import VoiceRuntime
from test_tile_windows import WINDOW
from test_tile_terminals import OTHER


class HideWindowsTests(unittest.TestCase):
    def test_exact_commands_and_no_fuzzy_crossover(self):
        with tempfile.TemporaryDirectory() as directory:
            matcher = IntentMatcher(Path(directory) / 'aliases.json')
            for category in ('terminals', 'apps'):
                command = category + ':hide'
                self.assertEqual(matcher.parse(f'Hide all {category}!').command, command)
                with patch('runtime.hide_windows', return_value='Hidden') as hide:
                    VoiceRuntime.execute(command, {'active': WINDOW})
                    hide.assert_called_once_with({'active': WINDOW}, category)
                with self.assertRaises(ValueError):
                    matcher.learn('some phrase', command)
            for phrase in ('hide apps', 'hide terminals', 'hide all termianals', 'hide all the apps'):
                self.assertIsNone(matcher.parse(phrase).command)
            self.assertEqual(matcher.parse('tile all apps').command, 'apps:tile')
            self.assertEqual(matcher.parse('tile all terminals').command, 'terminals:tile')

    def test_hides_only_selected_visible_category_without_tiling_or_restoring(self):
        excluded = [dict(OTHER, address='0x3', workspace={'id': 3}),
                    dict(OTHER, address='0x4', workspace={'id': -99, 'name': 'special:skipper-tile-2'}),
                    dict(OTHER, address='0x5', initialClass='io.github.gregorycoppola.Skipper'),
                    dict(WINDOW, address='0x6', mapped=False)]
        for category, target in [('terminals', WINDOW), ('apps', OTHER)]:
            clients = [WINDOW, OTHER, *excluded]
            moved = dict(target, workspace={'id': -99, 'name': 'special:skipper-tile-2'})
            after = [moved if c['address'] == target['address'] else c for c in clients]
            with patch('os_actions.run', side_effect=[json.dumps(clients), 'ok', json.dumps(after), '[]']) as run:
                self.assertIn(f'Hid 1 {category}', hide_windows({'active': WINDOW, 'clients': clients}, category))
                dispatches = [c.args[0][-1] for c in run.call_args_list if 'dispatch' in c.args[0]]
                self.assertEqual(len(dispatches), 1)
                self.assertIn('workspace = "special:skipper-tile-2"', dispatches[0])
                self.assertIn('address:' + target['address'], dispatches[0])

    def test_no_matches_and_stale_targets(self):
        with patch('os_actions.run') as run:
            self.assertIn('No visible', hide_windows({'active': WINDOW, 'clients': [WINDOW]}, 'apps'))
            run.assert_not_called()
        with patch('os_actions.run', return_value=json.dumps([dict(WINDOW, pid=999)])) as run:
            self.assertIn('Skipped 1', hide_windows({'active': WINDOW, 'clients': [WINDOW]}, 'terminals'))
            run.assert_called_once()

    def test_empty_workspace_capture_allows_restore(self):
        workspace = {'id': 2, 'name': '2', 'monitorID': 1}
        hidden = dict(WINDOW, workspace={'id': -99, 'name': 'special:skipper-tile-2'})
        with patch('os_actions.run', side_effect=['{}', json.dumps(workspace), json.dumps([hidden])]):
            context = capture_window_context()
        self.assertEqual(context['active']['workspace']['id'], 2)
        self.assertEqual(context['active']['monitor'], 1)
        self.assertEqual(context['clients'], [hidden])


class HideCurrentWindowTests(unittest.TestCase):
    def test_phrase_and_runtime_keep_captured_context(self):
        with tempfile.TemporaryDirectory() as directory:
            matcher = IntentMatcher(Path(directory) / 'aliases.json')
            result = matcher.parse('Hide this window!')
            self.assertEqual(result.command, 'window:hide')
            self.assertEqual(result.intent.type, 'hide_window')
            self.assertIsNone(matcher.parse('hide this windo').command)
        context = {'active': WINDOW, 'clients': [WINDOW, OTHER]}
        with patch('runtime.hide_current_window', return_value='Hidden') as action:
            VoiceRuntime.execute('window:hide', context)
            action.assert_called_once_with(context)

    def test_hides_captured_terminal_or_app_despite_focus_change(self):
        from os_actions import hide_current_window
        for target in (WINDOW, OTHER):
            hidden = dict(target, workspace={'id': -99, 'name': 'special:skipper-tile-2'})
            clients = [OTHER, WINDOW]
            updated = [hidden if c['address'] == target['address'] else c for c in clients]
            with patch('os_actions.run', side_effect=[json.dumps(clients), 'ok', json.dumps(updated), '[]']) as run:
                self.assertIn('Hid this window', hide_current_window({'active': target, 'clients': clients}))
                dispatches = [call.args[0][-1] for call in run.call_args_list if 'dispatch' in call.args[0]]
                self.assertEqual(len(dispatches), 1)
                self.assertIn('address:' + target['address'], dispatches[0])
                self.assertFalse(any('activewindow' in call.args[0] for call in run.call_args_list))

    def test_stale_or_missing_target_never_hides_another_window(self):
        from os_actions import hide_current_window
        for clients in ([], [dict(WINDOW, pid=999)], [dict(WINDOW, stableId='new')],
                        [dict(WINDOW, workspace={'id': 3})]):
            with patch('os_actions.run', return_value=json.dumps(clients)) as run:
                self.assertIn('No window was hidden', hide_current_window({'active': WINDOW}))
                run.assert_called_once()
        for context in (None, {'active': {}}, {'active': dict(WINDOW, workspace={'id': -99})}):
            with patch('os_actions.run') as run, self.assertRaises(RuntimeError):
                hide_current_window(context)
            run.assert_not_called()
