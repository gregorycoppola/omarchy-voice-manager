import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from installed_apps import discover_installed_apps, app_suggestions
from intent_matching import IntentMatcher
from open_arguments import parse_open
from launch_options import open_with_options


class OpenArgumentsTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.path = self.root / 'chromium.desktop'
        self.path.write_text('[Desktop Entry]\nType=Application\nName=Chromium\nGenericName=Web Browser\nExec=true\nStartupWMClass=chromium\n')
        self.apps = discover_installed_apps(roots=(self.root,), for_picker=True)
        self.app = self.apps.apps[0]
        self.matcher = IntentMatcher(self.root / 'aliases.json')

    def test_optional_arguments_and_literal_installed_names(self):
        for phrase, workspace, tile in [('open chromium', 'current', False),
                ('open chromium in this workspace', 'current', False),
                ('open chromium in workspace 3 and tile', '3', True),
                ('launch chromium and tile', 'current', True)]:
            result = parse_open(phrase, self.matcher, self.apps.expansions)
            self.assertEqual(result.command, 'desktop-app:chromium')
            self.assertEqual(result.launch_options, dict(workspace=workspace, tile=tile))
            self.assertEqual(result.to_dict()['launch_options'], result.launch_options)
        self.assertEqual(app_suggestions(self.apps)[0]['text'], 'open Chromium')
        self.assertNotIn('open web browser', app_suggestions(self.apps)[0]['forms'])
        for phrase in ['open chrome', 'open chromium in workspace 0',
                       'open chromium in workspace -1', 'open chromium in workspace 3; touch /tmp/nope',
                       'open chromium in workspace 9999999999']:
            result = parse_open(phrase, self.matcher, self.apps.expansions)
            self.assertIsNone(result.command, phrase)

    def test_literal_name_with_punctuation_is_executable(self):
        self.path.write_text('[Desktop Entry]\nType=Application\nName=Xournal++\nExec=true\n')
        apps = discover_installed_apps(roots=(self.root,), for_picker=True)
        text = app_suggestions(apps)[0]['text'] + ' in this workspace'
        self.assertEqual(parse_open(text, self.matcher, apps.expansions).command, 'desktop-app:chromium')

    def test_terminal_alias_uses_only_an_available_configured_terminal(self):
        (self.root / 'foot.desktop').write_text(
            '[Desktop Entry]\nType=Application\nName=Foot\nExec=true\nCategories=TerminalEmulator;\n')
        apps = discover_installed_apps(roots=(self.root,), for_picker=True)
        with patch('installed_apps.configured_terminal_id', return_value='foot'), \
             patch('open_arguments.configured_terminal_id', return_value='foot'):
            rows = app_suggestions(apps)
            self.assertEqual(rows[0]['text'], 'open terminal')
            self.assertIn('Foot', rows[0]['description'])
            self.assertTrue(any(row['text'] == 'open Foot' for row in rows))
            result = parse_open('open terminal in workspace 3 and tile', self.matcher, apps.expansions)
            self.assertEqual(result.command, 'terminal:new')
            self.assertEqual(result.launch_options, {'workspace': '3', 'tile': True})
        with patch('installed_apps.configured_terminal_id', return_value='missing'), \
             patch('open_arguments.configured_terminal_id', return_value='missing'):
            self.assertFalse(any(row['command'] == 'terminal:new' for row in app_suggestions(apps)))
            self.assertIsNone(parse_open('open terminal', self.matcher, apps.expansions).command)

    def test_picker_includes_launchable_dbus_and_terminal_apps(self):
        for name, flag in [('Tool', 'Terminal=true'), ('Viewer', 'DBusActivatable=true')]:
            (self.root / (name + '.desktop')).write_text(
                '[Desktop Entry]\nType=Application\nName=' + name + '\nExec=true\n' + flag + '\n')
        apps = discover_installed_apps(roots=(self.root,), for_picker=True)
        self.assertEqual({app.name for app in apps.apps}, {'Chromium', 'Tool', 'Viewer'})

    def test_stale_and_hidden_apps_are_not_offered(self):
        for name, extra in [('gone', 'Exec=skipper-test-nonexistent-executable\n'),
                            ('hidden', 'Exec=true\nHidden=true\n')]:
            (self.root / (name + '.desktop')).write_text('[Desktop Entry]\nType=Application\nName=' + name + '\n' + extra)
        apps = discover_installed_apps(roots=(self.root,), for_picker=True)
        self.assertEqual([a.name for a in apps.apps], ['Chromium'])
        self.path.unlink()
        self.assertFalse(discover_installed_apps(roots=(self.root,), for_picker=True).apps)

    def test_moves_only_new_window_and_tiles_destination(self):
        old = dict(address='0x1', pid=10, stableId='old', workspace={'id': 1}, **{'class': 'chromium'})
        new = dict(address='0x2', pid=10, stableId='new', workspace={'id': 1}, **{'class': 'chromium'})
        moved = dict(new, workspace={'id': 3})
        other = dict(address='0x3', workspace={'id': 3})
        with patch('launch_options.launch_entry'), \
             patch('launch_options.desktop.run', side_effect=[json.dumps([old]), json.dumps([old, new]), json.dumps([old, moved, other])]), \
             patch('launch_options.desktop.move_window_workspace') as move, \
             patch('launch_options.desktop.tile_open_windows') as tile, \
             patch('launch_options.desktop.focus_named_window') as focus:
            open_with_options('desktop-app:chromium', dict(workspace='3', tile=True), {}, self.app)
        move.assert_called_once_with(new, 3)
        tile.assert_called_once_with({'active': moved, 'clients': [old, moved, other]})
        focus.assert_called_once_with(moved)

    def test_new_tiled_app_is_raised_above_existing_floating_windows(self):
        old = dict(address='0x1', pid=10, stableId='old', workspace={'id': 3},
                   floating=True, **{'class': 'chromium'})
        new = dict(address='0x2', pid=10, stableId='new', workspace={'id': 3},
                   floating=False, **{'class': 'chromium'})
        captures = iter(([old], [old, new], [old, new], [old, new]))
        def run(argv):
            return json.dumps(next(captures)) if argv[1] == 'clients' else ''
        with patch('launch_options.launch_entry'), \
             patch('launch_options.desktop.run', side_effect=run) as dispatch, \
             patch('launch_options.desktop.move_window_workspace'), \
             patch('launch_options.desktop.focus') as focus:
            open_with_options('desktop-app:chromium', dict(workspace='3'), {}, self.app)
        commands = [call.args[0][2] for call in dispatch.call_args_list
                    if call.args[0][1] == 'dispatch']
        self.assertEqual(commands, [
            'hl.dsp.window.float({ action = "on", window = "address:0x2" })',
            'hl.dsp.window.alter_zorder({ mode = "top", window = "address:0x2" })'])
        focus.assert_called_once_with(new)

    def test_existing_window_is_never_substituted(self):
        old = dict(address='0x1', **{'class': 'chromium'})
        launcher = Mock()
        launcher.poll.return_value = None
        with patch('launch_options.launch_entry', return_value=launcher), \
             patch('launch_options.desktop.run', return_value=json.dumps([old])), \
             patch('launch_options.time.monotonic', side_effect=[0, 0, 11]), \
             patch('launch_options.time.sleep'), \
             patch('launch_options.desktop.move_window_workspace') as move:
            with self.assertRaisesRegex(RuntimeError, 'no identifiable new'):
                open_with_options('desktop-app:chromium', dict(workspace='current'), {'active': {'workspace': {'id': 4}}}, self.app)
        move.assert_not_called()

    def test_missing_captured_workspace_does_not_launch(self):
        with patch('launch_options.launch_entry') as launch:
            with self.assertRaisesRegex(RuntimeError, 'regular workspace'):
                open_with_options('desktop-app:chromium', dict(workspace='current'), {}, self.app)
        launch.assert_not_called()
