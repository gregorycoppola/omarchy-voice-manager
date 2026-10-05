import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from intent_matching import IntentMatcher
from os_actions import maximize_current_window, parse_command

TARGET = {"address": "0x1", "pid": 100, "class": "chromium", "stableId": "one", "monitor": 0}


class MaximizeWindowTests(unittest.TestCase):
    def test_fullscreen_and_repeated_maximize_stay_on_same_screen(self):
        for state in (0, 1, 2):
            current = dict(TARGET, fullscreen=state, fullscreenClient=state)
            maximized = dict(TARGET, fullscreen=1, fullscreenClient=1, floating=True)
            with patch("os_actions.run", side_effect=[json.dumps([current]), "ok", "ok", "ok", "ok", "ok", json.dumps(maximized), json.dumps(maximized)]) as run:
                self.assertEqual(maximize_current_window(TARGET), "Maximized this window")
                dispatches = [c.args[0][-1] for c in run.call_args_list if "dispatch" in c.args[0]]
                self.assertEqual(len(dispatches), 5)
                self.assertIn('action = "set"', dispatches[2])
                self.assertIn('internal = 1, client = 1', dispatches[2])
                self.assertIn('alter_zorder', dispatches[3])
                self.assertTrue(all('address:0x1' in d for d in dispatches))
                self.assertFalse(any('move' in d for d in dispatches))

    def test_stale_or_invalid_target_never_dispatches(self):
        for clients in ([], [dict(TARGET, pid=999)], [dict(TARGET, stableId="replacement")]):
            with patch("os_actions.run", return_value=json.dumps(clients)) as run:
                with self.assertRaisesRegex(RuntimeError, "closed or changed"):
                    maximize_current_window(TARGET)
                run.assert_called_once()
        with patch("os_actions.run") as run:
            with self.assertRaises(RuntimeError):
                maximize_current_window(None)
            run.assert_not_called()
