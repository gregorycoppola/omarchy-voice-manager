import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch

from os_actions import execute_command, launch_desktop


class DesktopLaunchTests(unittest.TestCase):
    def test_launcher_has_no_inherited_capture_pipes_and_is_reaped_off_thread(self):
        with patch('os_actions.subprocess.Popen') as popen, patch('os_actions.threading.Thread') as thread:
            process = launch_desktop(Path('/tmp/example.desktop'))
            popen.assert_called_once_with(['gio', 'launch', '/tmp/example.desktop'],
                                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL, start_new_session=True)
            thread.assert_called_once_with(target=process.wait, daemon=True)
            thread.return_value.start.assert_called_once()
            process.wait.assert_not_called()

    def test_appeared_window_succeeds_even_when_launcher_is_still_running(self):
        for command, app_class in [('browser', 'chromium'), ('discord', 'discord'),
                                   ('x', 'chrome-x.com__-Default')]:
            window = {'class': app_class, 'address': '0x1'}
            launcher = Mock()
            launcher.poll.return_value = None
            with self.subTest(command=command), \
                 patch('os_actions.run', side_effect=[json.dumps([{'name': 'DP-1', 'activeWorkspace': {'id': 1}}]), '[]', '[]', json.dumps([window])]), \
                 patch('os_actions.Path.is_file', return_value=True), \
                 patch('os_actions.launch_desktop', return_value=launcher) as launch, \
                 patch('os_actions.time.sleep'), patch('os_actions.present_browser') as present:
                self.assertIn('Opened', execute_command(command))
                launch.assert_called_once()
                present.assert_called_once()
                self.assertEqual(present.call_args.args[0], window)
                launcher.wait.assert_not_called()
                launcher.kill.assert_not_called()

    def test_failed_launcher_without_window_reports_failure(self):
        launcher = Mock()
        launcher.poll.return_value = 1
        with patch('os_actions.run', side_effect=[json.dumps([{'name': 'DP-1', 'activeWorkspace': {'id': 1}}]), '[]', '[]']), \
             patch('os_actions.Path.is_file', return_value=True), \
             patch('os_actions.launch_desktop', return_value=launcher), \
             patch('os_actions.present_browser') as present:
            with self.assertRaisesRegex(RuntimeError, 'launcher failed'):
                execute_command('browser')
            present.assert_not_called()

    def test_missing_window_is_bounded_even_when_launcher_does_not_exit(self):
        with patch('os_actions.run', side_effect=[json.dumps([{'name': 'DP-1', 'activeWorkspace': {'id': 1}}]), '[]']), \
             patch('os_actions.Path.is_file', return_value=True), \
             patch('os_actions.launch_desktop'), patch('os_actions.time.monotonic', side_effect=[0, 11]):
            with self.assertRaisesRegex(RuntimeError, 'no browser window appeared'):
                execute_command('browser')
