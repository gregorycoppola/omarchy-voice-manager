"""All opened windows share maximized, explicitly raised presentation."""
import json
import unittest
from unittest.mock import patch
from os_actions import present_new_terminal, maximize_foreground

NEW = {'class': 'foot', 'address': '0x1', 'pid': 10, 'stableId': 'new',
       'monitor': 1, 'workspace': {'id': 2}, 'floating': False}

class NewTerminalTests(unittest.TestCase):
    def test_new_terminal_uses_common_maximized_presentation(self):
        with patch('os_actions.maximize_foreground') as present:
            present_new_terminal(NEW)
            present.assert_called_once_with(NEW)

    def test_float_maximize_raise_then_focus_for_terminal_and_webapp(self):
        for app_class in ('foot', 'chrome-discord.com__channels_@me-Default', 'chromium'):
            target = dict(NEW, **{'class': app_class})
            active = dict(target, floating=True, fullscreen=1, fullscreenClient=1)
            responses = [json.dumps([target]), 'ok', 'ok', 'ok', 'ok', 'ok', json.dumps(active), json.dumps(active)]
            with patch('os_actions.run', side_effect=responses) as run:
                maximize_foreground(target)
            calls = [call.args[0][2] for call in run.call_args_list if 'dispatch' in call.args[0]]
            self.assertIn('window.float', calls[1])
            self.assertIn('internal = 1, client = 1', calls[2])
            self.assertIn('alter_zorder', calls[3])
            self.assertIn('mode = "top"', calls[3])
            self.assertIn('hl.dsp.focus', calls[4])
            self.assertTrue(all('address:0x1' in call for call in calls))

    def test_unconfirmed_foreground_state_reports_failure(self):
        for wrong in (dict(NEW, floating=False, fullscreen=1, fullscreenClient=1),
                      dict(NEW, floating=True, fullscreen=0, fullscreenClient=0)):
            with patch('os_actions.run', side_effect=[json.dumps([NEW]), 'ok', 'ok', 'ok', 'ok', json.dumps(wrong)]), \
                 patch('os_actions.focus'):
                with self.assertRaisesRegex(RuntimeError, 'confirm'):
                    maximize_foreground(NEW)

    def test_replaced_terminal_is_not_shown(self):
        with patch('os_actions.run', return_value=json.dumps([dict(NEW, pid=99)])), patch('os_actions.focus') as focus:
            with self.assertRaises(RuntimeError):
                present_new_terminal(NEW)
            focus.assert_not_called()
