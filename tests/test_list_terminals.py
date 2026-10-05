import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from intent_matching import IntentMatcher
from os_actions import open_window_entries, focus_listed_window, focus
from runtime import VoiceRuntime

A = dict(address='0x1', pid=1, stableId='one', title='[working] Fix layout | skipper', workspace={'id': 2}, **{'class': 'foot'})
B = dict(address='0x2', pid=2, stableId='two', title='Review parser | skipper', workspace={'id': 4}, **{'class': 'Alacritty'})
C = dict(address='0x3', pid=3, stableId='three', title='Browser', **{'class': 'chromium'})


class ListTerminalsTests(unittest.TestCase):
    def test_generic_app_argument_and_exact_class_matching(self):
        spotify = dict(C, address='0x4', **{'class':'com.spotify.Client','initialClass':'Spotify'})
        with patch('os_actions.run', return_value=json.dumps([A,C,spotify])):
            self.assertEqual([row['address'] for row in open_window_entries(application='spotify')], ['0x4'])
            self.assertEqual(open_window_entries(application='spot'), [])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            matcher = IntentMatcher(root/'aliases.json')
            for verb, command in [('list','list-all:spotify'),('show','show-all:spotify')]:
                result = matcher.parse(f'{verb} all spotify')
                self.assertEqual(result.command, command)
                self.assertEqual(dict(result.intent.arguments), {'application':'spotify'})
            self.assertIsNone(matcher.parse('do not list all spotify').command)
            app = VoiceRuntime(root, root/'status.json')
            app.state['monitor'] = 'DP-1'
            with patch('runtime.open_window_entries', return_value=[]) as entries, \
                 patch('runtime.GLib.idle_add', side_effect=lambda fn,*args:fn(*args)), \
                 patch.object(app, 'focused_monitor', return_value='DP-2'):
                app.interpret('list all spotify', {'clients':[]})
            entries.assert_called_once_with(application='spotify')
            self.assertEqual(app.state['message'], 'There are no open spotify windows.')
            self.assertEqual(app.state['monitor'], 'DP-1')

    def test_list_x_filter_and_empty_confirmation(self):
        x = dict(C, address='0x4', **{'class':'chrome-x.com__-Default'})
        with patch('os_actions.run', return_value=json.dumps([A,C,x])):
            self.assertEqual([row['address'] for row in open_window_entries(application='x')], ['0x4'])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            matcher = IntentMatcher(root/'aliases.json')
            for phrase in ('list all X','list X','list all twitter'):
                self.assertEqual(matcher.parse(phrase).command, 'x:list')
            app = VoiceRuntime(root, root/'status.json')
            with patch('runtime.open_window_entries', return_value=[]) as entries, \
                 patch('runtime.GLib.idle_add', side_effect=lambda fn,*args:fn(*args)):
                app.interpret('list all X', {'clients':[]})
            entries.assert_called_once_with(application='x')
            self.assertEqual(app.state['message'], 'There are no open X windows.')

    def test_browser_list_includes_hidden_and_other_workspaces_without_focusing(self):
        firefox = dict(C, address='0x4', workspace={'id':5}, **{'class':'firefox'})
        hidden = dict(C, visible=False, workspace={'id':-9,'name':'special:skipper-tile-2'})
        webapp = dict(C, address='0x5', **{'class':'chrome-x.com__-Default'})
        with patch('os_actions.run', return_value=json.dumps([A,B,hidden,firefox,webapp])) as run:
            rows = open_window_entries(browsers_only=True)
        self.assertEqual({r['address'] for r in rows}, {'0x3','0x4'})
        run.assert_called_once_with(['hyprctl','clients','-j'])

    def test_browser_list_phrases_and_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            matcher = IntentMatcher(root/'aliases.json')
            for phrase in ('list all browsers','list browsers','list all browser windows','what browsers are open'):
                result = matcher.parse(phrase)
                self.assertEqual(result.command, 'browsers:list')
                self.assertEqual(result.canonical_plan, [{'intent':'window.list','arguments':{
                    'scope':'open_windows','application':'browser'}}])
            app = VoiceRuntime(root, root/'status.json')
            with patch('runtime.open_window_entries', return_value=[]) as entries, \
                 patch('runtime.GLib.idle_add', side_effect=lambda fn,*args:fn(*args)), \
                 patch.object(app, 'execute') as execute:
                app.interpret('list all browsers', {'clients':[]})
            entries.assert_called_once_with(browsers_only=True)
            execute.assert_not_called()
            self.assertEqual(app.state['state'], 'WindowList')
            self.assertEqual(app.state['message'], 'There are no open browsers.')

    def test_filter_workspace_and_unique_title_derived_names(self):
        with patch('os_actions.run', return_value=json.dumps([A, B, C])):
            rows = open_window_entries(terminals_only=True)
        self.assertEqual([r['address'] for r in rows], ['0x1', '0x2'])
        self.assertEqual([r['workspace'] for r in rows], ['2', '4'])
        self.assertIn('fix layout', rows[0]['spoken_names'])
        self.assertNotIn('skipper', rows[0]['spoken_names'])
        self.assertNotIn('skipper terminal', rows[0]['spoken_names'])
        self.assertFalse(any('working' in name for name in rows[0]['spoken_names']))
        self.assertEqual(rows[0]['title'], A['title'])

    def test_unnamed_terminal_still_listed(self):
        with patch('os_actions.run', return_value=json.dumps([dict(A, title='')])):
            row = open_window_entries(terminals_only=True)[0]
        self.assertEqual(row['spoken_names'], [])
        self.assertIn('No spoken name', row['names_note'])

    def test_schema_parser_and_runtime_list_do_not_execute_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            matcher = IntentMatcher(root / 'aliases.json')
            for phrase in ('list the terminals', 'list terminals', 'what terminals are open'):
                result = matcher.parse(phrase)
                self.assertEqual(result.canonical_plan, [{'intent': 'window.list', 'arguments': {
                    'scope': 'open_windows', 'application': 'terminal'}}])
            app = VoiceRuntime(root, root / 'status.json')
            with patch('runtime.open_window_entries', return_value=[{'address': '0x1'}]) as entries, \
                 patch('runtime.GLib.idle_add', side_effect=lambda fn, *args: fn(*args)), \
                 patch.object(app, 'execute') as execute:
                app.interpret('list the terminals', {'clients': []})
            entries.assert_called_once_with(terminals_only=True)
            execute.assert_not_called()
            self.assertEqual(app.state['state'], 'WindowList')
            self.assertEqual(app.state['window_list'], [{'address': '0x1'}])

    def test_focus_revalidates_saved_identity(self):
        with patch('os_actions.run', return_value=json.dumps([dict(A, pid=99)])), \
             patch('os_actions.focus') as focus:
            with self.assertRaisesRegex(RuntimeError, 'replaced'):
                focus_listed_window('0x1', expected=A)
            focus.assert_not_called()
        with patch('os_actions.run', return_value=json.dumps([A])), patch('os_actions.focus') as focus:
            focus_listed_window('0x1', expected=A)
            focus.assert_called_once_with(A)

    def test_focus_listed_tiled_window_rises_above_floating_peer(self):
        tiled = dict(A, floating=False)
        floating = dict(A, address='0x4', pid=4, stableId='four', floating=True)
        with patch('os_actions.run', return_value=json.dumps([tiled, floating])) as run, \
             patch('os_actions.focus') as focus:
            focus_listed_window('0x1', expected=A)
        commands = [call.args[0][2] for call in run.call_args_list[1:]]
        self.assertIn('window.float', commands[0])
        self.assertIn('alter_zorder', commands[1])
        focus.assert_called_once_with(tiled)

    def test_chooser_releases_focus_before_focusing_selected_window(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = VoiceRuntime(root, root / 'status.json')
            app.state.update(state='WindowList', window_list=[A])
            with patch('runtime.GLib.timeout_add') as schedule, \
                 patch('runtime.focus_listed_window', return_value='Focused window') as focus:
                app.focus_listed_window('0x1')
                self.assertEqual(app.state['state'], 'Working')
                self.assertEqual(app.state['window_list'], [])
                focus.assert_not_called()
                delay, callback, address, expected = schedule.call_args.args
                self.assertGreater(delay, 0)
                self.assertFalse(callback(address, expected))
                focus.assert_called_once_with('0x1', expected=A)
                self.assertEqual(app.state['state'], 'Ready')

    def test_focus_allows_hyprland_to_report_the_new_active_window(self):
        with patch('os_actions.run', side_effect=['ok', json.dumps({'address': '0x2'}),
                                                 json.dumps({'address': '0x1'})]) as run, \
             patch('os_actions.time.sleep') as sleep:
            focus(A)
        self.assertEqual(run.call_count, 3)
        sleep.assert_called_once()
