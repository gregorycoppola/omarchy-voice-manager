import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from os_actions import terminal_close_target, close_terminal, parse_command
from settings import Settings

A = {'class':'foot', 'address':'0x1', 'pid':100, 'title':'Editor', 'focusHistoryID':2, 'stableId':'one'}
B = {'class':'foot', 'address':'0x2', 'pid':200, 'title':'Shell', 'focusHistoryID':0, 'stableId':'two'}


class TerminalCloseTests(unittest.TestCase):
    def test_phrase_routing(self):
        self.assertEqual(parse_command('close terminal'), 'close:terminal')
        self.assertEqual(parse_command('Close this terminal!'), 'close:terminal_current')

    def test_current_and_recent_are_distinct(self):
        context = {'active':A, 'clients':[A,B]}
        self.assertEqual(terminal_close_target('close:terminal_current', context), A)
        self.assertEqual(terminal_close_target('close:terminal', context), B)

    def test_current_never_falls_back_to_another_terminal(self):
        with self.assertRaisesRegex(RuntimeError, 'not a terminal'):
            terminal_close_target('close:terminal_current', {'active':{'class':'chromium'}, 'clients':[B]})
        with self.assertRaises(RuntimeError):
            terminal_close_target('close:terminal', None)
        with self.assertRaisesRegex(RuntimeError, 'No open'):
            terminal_close_target('close:terminal', {'clients':[]})

    def test_confirmed_target_does_not_follow_new_focus(self):
        with patch('os_actions.run', side_effect=[json.dumps([B,A]), 'ok']) as run:
            close_terminal(A)
            self.assertIn('address:0x1', run.call_args_list[1].args[0][2])
            self.assertIn('window.close', run.call_args_list[1].args[0][2])

    def test_closed_or_replaced_window_never_redirects_close(self):
        with patch('os_actions.run', return_value=json.dumps([B])) as run:
            self.assertIn('already closed', close_terminal(A))
            run.assert_called_once()
        for replacement in [dict(A, pid=999), dict(A, stableId='new'), dict(A, **{'class':'chromium'})]:
            with patch('os_actions.run', return_value=json.dumps([replacement])) as run:
                with self.assertRaisesRegex(RuntimeError, 'changed'):
                    close_terminal(A)
                run.assert_called_once()

    def test_invalid_address_never_dispatches(self):
        with patch('os_actions.run') as run:
            with self.assertRaises(ValueError):
                close_terminal(dict(A, address='0x1"'))
            run.assert_not_called()

    def test_preference_default_reload_and_corrupt_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'settings.json'
            settings = Settings(path)
            self.assertTrue(settings.confirm_terminal_close)
            settings.set_confirm_terminal_close(False)
            self.assertFalse(Settings(path).confirm_terminal_close)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            path.write_text('broken')
            settings = Settings(path)
            self.assertTrue(settings.confirm_terminal_close)
            with self.assertRaises(ValueError):
                settings.set_confirm_terminal_close(False)
            self.assertEqual(path.read_text(), 'broken')
