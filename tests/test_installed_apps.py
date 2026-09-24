"""Installed desktop entries become exact, bounded launch commands."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from installed_apps import discover_installed_apps, reserved_app_forms
from intent_matching import IntentMatcher
from os_actions import open_installed_app
from runtime import VoiceRuntime


def desktop(root, identifier, text):
    path = root / (identifier + '.desktop')
    path.write_text('[Desktop Entry]\nType=Application\n' + text)
    return path


class InstalledAppTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.user = self.root / 'user'
        self.shared = self.root / 'shared'
        self.user.mkdir()
        self.shared.mkdir()

    def test_visible_entries_are_exact_and_ambiguous_names_are_omitted(self):
        desktop(self.user, 'com.example.Paint', 'Name=Paint!\nGenericName=Picture editor\nExec=paint\n')
        desktop(self.user, 'org.example.Draw', 'Name=Paint\nExec=draw\n')
        desktop(self.user, 'org.example.Reader', 'Name=Book Reader\nGenericName=Reader\nExec=reader\n')
        apps = discover_installed_apps(roots=(self.user,), reserved_forms={'reader'})
        by_id = {app.desktop_id: app for app in apps.apps}
        self.assertEqual(by_id['com.example.Paint'].forms, ('picture editor',))
        self.assertNotIn('org.example.Draw', by_id)
        self.assertEqual(by_id['org.example.Reader'].forms, ('book reader',))
        matcher = IntentMatcher(self.root / 'aliases.json')
        for phrase in ('open picture editor', 'launch picture editor', 'open book reader'):
            result = matcher.parse(phrase, apps.expansions)
            self.assertEqual(result.method, 'exact')
            self.assertEqual(result.intent.type, 'open_installed_app')
        self.assertIsNone(matcher.parse('open paint', apps.expansions).command)
        self.assertIsNone(matcher.parse('open pictur editor', apps.expansions).command)
        self.assertIsNone(matcher.parse('do not open book reader', apps.expansions).command)

    def test_hidden_terminal_missing_tryexec_and_user_override_are_excluded(self):
        desktop(self.shared, 'org.example.Visible', 'Name=Visible\nExec=visible\n')
        desktop(self.user, 'org.example.Visible', 'Name=Visible\nHidden=true\nExec=visible\n')
        desktop(self.user, 'org.example.Terminal', 'Name=Terminal tool\nTerminal=true\nExec=tool\n')
        desktop(self.user, 'org.example.Missing', 'Name=Missing tool\nTryExec=missing-executable\nExec=tool\n')
        desktop(self.user, 'org.example.Dbus', 'Name=Dbus tool\nDBusActivatable=true\nExec=tool\n')
        apps = discover_installed_apps(roots=(self.user, self.shared))
        self.assertFalse(apps.apps)

    def test_builtin_open_phrase_remains_owner(self):
        desktop(self.user, 'org.example.Chrome', 'Name=Chrome\nExec=chrome\n')
        apps = discover_installed_apps(roots=(self.user,), reserved_forms=reserved_app_forms({'open chrome': 'browser'}))
        self.assertFalse(apps.apps)

    def test_launcher_uses_selected_path_and_reports_failures(self):
        path = desktop(self.user, 'org.example.Reader', 'Name=Book Reader\nExec=reader\n')
        app = discover_installed_apps(roots=(self.user,)).apps[0]
        launcher = Mock()
        launcher.poll.return_value = None
        with patch('os_actions.launch_desktop', return_value=launcher) as launch, patch('os_actions.time.sleep'):
            self.assertEqual(open_installed_app(app), 'Opening Book Reader')
        launch.assert_called_once_with(path)
        launcher.poll.return_value = 1
        with patch('os_actions.launch_desktop', return_value=launcher), patch('os_actions.time.sleep'):
            with self.assertRaisesRegex(RuntimeError, 'launcher failed'):
                open_installed_app(app)
        path.unlink()
        with patch('os_actions.launch_desktop') as launch:
            with self.assertRaisesRegex(RuntimeError, 'no longer installed'):
                open_installed_app(app)
            launch.assert_not_called()

    def test_runtime_routes_only_current_discovered_target(self):
        app_entry = desktop(self.user, 'org.example.Reader', 'Name=Book Reader\nExec=reader\n')
        apps = discover_installed_apps(roots=(self.user,))
        runtime = VoiceRuntime(self.root, self.root / 'status.json')
        with patch('runtime.discover_installed_apps', return_value=apps), \
             patch('runtime.GLib.idle_add', side_effect=lambda fn, *args: fn(*args)), \
             patch('runtime.open_installed_app', return_value='Opening Book Reader') as launch:
            runtime.interpret('open book reader', {})
        launch.assert_called_once_with(apps.apps[0])
        self.assertEqual(runtime.state['state'], 'Ready')
        self.assertEqual(runtime.state['intent']['arguments']['desktop'], 'org.example.Reader')
        self.assertFalse((self.root / 'aliases.json').exists())
        app_entry.unlink()
