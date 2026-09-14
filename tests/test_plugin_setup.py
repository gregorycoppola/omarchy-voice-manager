import json
import os
import shutil
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from plugin_setup import install_integration, uninstall_integration
from os_actions import main_monitor

ROOT = Path(__file__).resolve().parents[1]


class PluginSetupTests(unittest.TestCase):
    def test_install_repeat_uninstall_preserves_user_configuration_and_data(self):
        with tempfile.TemporaryDirectory(prefix='skipper setup ') as temporary:
            home = Path(temporary)
            config, data = home/'config', home/'data'
            bindings = config/'hypr/bindings.lua'
            bindings.parent.mkdir(parents=True)
            original = '-- User bindings\n'
            bindings.write_text(original)
            receipt = install_integration(ROOT, home, config, data, shortcut=True, autostart=True)
            first = bindings.read_text()
            install_integration(ROOT, home, config, data, shortcut=True, autostart=True)
            self.assertEqual(bindings.read_text(), first)
            self.assertEqual(first.count('-- BEGIN Skipper'), 1)
            saved = data/'skipper/aliases.json'
            saved.write_text('{"example":"saved"}')
            self.assertTrue((home/'.local/bin/skipper').is_file())
            self.assertTrue((config/'autostart/skipper.desktop').is_file())
            self.assertEqual(uninstall_integration(data), [])
            self.assertEqual(bindings.read_text(), original)
            self.assertEqual(saved.read_text(), '{"example":"saved"}')
            self.assertFalse(receipt.exists())
            self.assertFalse((home/'.local/bin/skipper').exists())
            self.assertFalse((config/'autostart/skipper.desktop').exists())

    def test_conflicts_require_explicit_replace_and_modified_files_survive_removal(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            config, data = home/'config', home/'data'
            binary = home/'.local/bin/skipper'
            binary.parent.mkdir(parents=True)
            binary.write_text('user-owned launcher')
            with self.assertRaisesRegex(RuntimeError, 'replace-existing'):
                install_integration(ROOT, home, config, data)
            self.assertEqual(binary.read_text(), 'user-owned launcher')
            install_integration(ROOT, home, config, data, replace=True)
            self.assertTrue(any(p.name == 'skipper' for p in (data/'skipper/install-backups').rglob('*')))
            binary.write_text('edited launcher')
            self.assertTrue(uninstall_integration(data))
            self.assertEqual(binary.read_text(), 'edited launcher')

    def test_single_monitor_and_explicit_monitor_policy(self):
        screen = {'id': 0, 'name': 'eDP-1', 'activeWorkspace': {'id': 1}}
        with patch('os_actions.MAIN_MONITOR', ''):
            self.assertEqual(main_monitor([screen]), screen)
        with patch('os_actions.MAIN_MONITOR', 'missing'):
            with self.assertRaisesRegex(RuntimeError, 'not connected'):
                main_monitor([screen])


    def test_clean_plugin_launcher_uses_external_environment_and_preserves_arguments(self):
        with tempfile.TemporaryDirectory(prefix='skipper plugin ') as directory:
            directory = Path(directory)
            plugin, data = directory/'plugin', directory/'data'
            plugin.mkdir()
            for name in ('launch.sh', 'launch-runtime.sh'):
                shutil.copy2(ROOT/name, plugin/name)
            python = data/'skipper/venv/bin/python'
            python.parent.mkdir(parents=True)
            python.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
            python.chmod(0o755)
            result = subprocess.run([str(plugin/'launch.sh'), '--show', 'argument with spaces'],
                                    env=dict(os.environ, XDG_DATA_HOME=str(data)), capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.splitlines(), [str(plugin/'runtime.py'), '--show', 'argument with spaces'])
            self.assertFalse((plugin/'.venv').exists())

    def test_root_and_development_manifests_share_identity(self):
        root = json.loads((ROOT/'manifest.json').read_text())
        development = json.loads((ROOT/'config/skipper-bar/manifest.json').read_text())
        self.assertEqual(root['id'], development['id'])
        self.assertEqual(root['version'], development['version'])
        self.assertTrue((ROOT/root['entryPoints']['barWidget']).is_file())
