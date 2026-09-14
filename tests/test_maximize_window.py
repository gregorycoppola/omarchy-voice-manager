import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from gui import Keety
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

    def test_exact_and_fuzzy_keep_captured_target(self):
        self.assertEqual(parse_command("Maximize this window!"), "maximize:current_window")
        with tempfile.TemporaryDirectory() as directory:
            matcher = IntentMatcher(Path(directory) / "aliases.json")
            for phrase, exact in [("maximize this window", True), ("maximize this windo", False)]:
                app = SimpleNamespace(model=object(), refresh_aliases=Mock(), matcher=matcher, finished=Mock(), offer_suggestion=Mock())
                with patch("gui.save_transcript", return_value=(phrase, {"audio_seconds":1,"transcribe_seconds":.1})), patch("gui.maximize_current_window", return_value="Maximized") as action, patch("gui.GLib.idle_add", side_effect=lambda cb,*args: cb(*args)):
                    Keety.convert(app, Path("test.wav"), commands=True, context={"active":TARGET})
                    action.assert_called_once_with(TARGET)
                    app.offer_suggestion.assert_not_called()
                    self.assertEqual(matcher.exact(phrase), 'maximize:current_window')

    def test_confirmation_targets_original_window(self):
        app = SimpleNamespace(finished=Mock())
        with patch("gui.maximize_current_window", return_value="Maximized") as action, patch("gui.close_terminal") as close, patch("gui.GLib.idle_add", side_effect=lambda cb,*args: cb(*args)):
            Keety.run_confirmed(app, Path("test.wav"), "maximize:current_window", TARGET)
            action.assert_called_once_with(TARGET)
            close.assert_not_called()
