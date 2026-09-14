import json
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from gui import Skipper
from intent_matching import IntentMatcher
from unittest.mock import patch
from os_actions import parse_command, window_target, move_other_screen

TARGET = {'address':'0x1', 'pid':100, 'class':'chromium', 'stableId':'one', 'monitor':0}
MONITORS = [{'id':0,'name':'eDP-1','activeWorkspace':{'id':1}},
            {'id':1,'name':'DP-1','activeWorkspace':{'id':2}}]


class MoveScreenTests(unittest.TestCase):
    def test_phrases(self):
        for text in ['Move to other screen!', 'move window to other screen', 'move this window to the other screen']:
            self.assertEqual(parse_command(text), 'move:other_screen')

    def test_target_is_snapshot_not_current_focus(self):
        context = {'active':dict(TARGET)}
        target = window_target(context)
        context['active']['address'] = '0x2'
        self.assertEqual(target['address'], '0x1')

    def test_moves_both_directions_to_active_workspace(self):
        for source, dest in [(0,1),(1,0)]:
            current = dict(TARGET, monitor=source)
            moved = dict(current, monitor=dest, workspace={'id': dest+1})
            responses = [json.dumps([current]), json.dumps(MONITORS), 'ok', 'ok', json.dumps([moved])]
            with patch('os_actions.run', side_effect=responses) as run, \
                 patch('os_actions.maximize_foreground') as maximize, patch('os_actions.tile_open_windows') as tile:
                self.assertEqual(move_other_screen(TARGET), 'Moved window to '+MONITORS[dest]['name'])
                maximize.assert_called_once_with(moved)
                tile.assert_not_called()
                self.assertEqual(run.call_args_list[2].args[0], ['hyprctl','dispatch',
                    f'hl.dsp.window.move({{ window = "address:0x1", workspace = "{dest+1}", follow = true }})'])

    def test_occupied_destination_retiles_only_its_workspace_and_focuses_arrival(self):
        moved = dict(TARGET, monitor=1, workspace={'id': 2})
        neighbor = dict(moved, address='0x2', stableId='two')
        elsewhere = dict(TARGET, address='0x3', workspace={'id': 1})
        hidden_workspace = dict(neighbor, address='0x4', workspace={'id': 9})
        unmapped = dict(neighbor, address='0x5', mapped=False)
        skipper = dict(neighbor, address='0x6', **{'class': 'io.github.gregorycoppola.Skipper'})
        clients = [moved, neighbor, elsewhere, hidden_workspace, unmapped, skipper]
        with patch('os_actions.run', side_effect=[json.dumps([TARGET]), json.dumps(MONITORS), 'ok', 'ok', json.dumps(clients)]), \
             patch('os_actions.maximize_foreground') as maximize, \
             patch('os_actions.tile_open_windows', return_value='Tiled 2 windows') as tile, \
             patch('os_actions.focus') as focus:
            move_other_screen(TARGET)
            tile.assert_called_once_with({'active': moved, 'clients': [moved, neighbor]})
            maximize.assert_not_called()
            focus.assert_called_once_with(moved)

    def test_replaced_arrival_is_not_arranged(self):
        moved = dict(TARGET, monitor=1, workspace={'id': 2}, stableId='replacement')
        with patch('os_actions.run', side_effect=[json.dumps([TARGET]), json.dumps(MONITORS), 'ok', 'ok', json.dumps([moved])]), \
             patch('os_actions.maximize_foreground') as maximize, patch('os_actions.tile_open_windows') as tile:
            with self.assertRaisesRegex(RuntimeError, 'Could not confirm'):
                move_other_screen(TARGET)
            maximize.assert_not_called()
            tile.assert_not_called()

    def test_single_screen_never_dispatches(self):
        with patch('os_actions.run', side_effect=[json.dumps([TARGET]), json.dumps(MONITORS[:1])]) as run:
            with self.assertRaisesRegex(RuntimeError, 'No other'):
                move_other_screen(TARGET)
            self.assertEqual(run.call_count,2)

    def test_missing_replaced_and_invalid_windows_do_not_move(self):
        for clients in [[], [dict(TARGET,pid=999)], [dict(TARGET,stableId='new')]]:
            with patch('os_actions.run', return_value=json.dumps(clients)) as run:
                with self.assertRaisesRegex(RuntimeError,'changed'):
                    move_other_screen(TARGET)
                run.assert_called_once()
        with patch('os_actions.run') as run:
            with self.assertRaises(RuntimeError):
                move_other_screen(dict(TARGET,address='0x1"'))
            run.assert_not_called()

    def test_invalid_workspace_does_not_dispatch(self):
        monitors = [MONITORS[0], dict(MONITORS[1],activeWorkspace={'id':-1})]
        with patch('os_actions.run',side_effect=[json.dumps([TARGET]),json.dumps(monitors)]) as run:
            with self.assertRaisesRegex(RuntimeError,'workspace'):
                move_other_screen(TARGET)
            self.assertEqual(run.call_count,2)


class MoveRoutingTests(unittest.TestCase):
    def test_exact_and_fuzzy_preserve_recording_context(self):
        with tempfile.TemporaryDirectory() as directory:
            matcher = IntentMatcher(Path(directory)/'aliases.json')
            for phrase, exact in [('move to other screen', True), ('move to other screan', False)]:
                app = SimpleNamespace(model=object(), refresh_aliases=Mock(), matcher=matcher, finished=Mock(), offer_suggestion=Mock())
                with patch('gui.save_transcript', return_value=(phrase, {'audio_seconds':1,'transcribe_seconds':.1})), \
                     patch('gui.move_other_screen', return_value='Moved') as move, \
                     patch('gui.GLib.idle_add', side_effect=lambda callback,*args: callback(*args)):
                    Skipper.convert(app, Path('test.wav'), commands=True, context={'active':TARGET})
                    move.assert_called_once_with(TARGET)
                    app.offer_suggestion.assert_not_called()
                    self.assertEqual(matcher.exact(phrase), 'move:other_screen')

    def test_fuzzy_confirmation_uses_captured_target(self):
        app = SimpleNamespace(finished=Mock())
        with patch('gui.move_other_screen', return_value='Moved') as move, \
             patch('gui.execute_command') as generic, \
             patch('gui.GLib.idle_add', side_effect=lambda callback,*args: callback(*args)):
            Skipper.run_confirmed(app, Path('test.wav'), 'move:other_screen', TARGET, True)
            move.assert_called_once_with(TARGET)
            generic.assert_not_called()
