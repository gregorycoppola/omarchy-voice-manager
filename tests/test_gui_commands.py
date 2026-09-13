"""Command-mode routing: save first, execute only on an exact opted-in match."""
from pathlib import Path
from types import SimpleNamespace
import unittest
import threading
from unittest.mock import Mock, patch

from gui import Keety


class CommandRoutingTests(unittest.TestCase):
    def route(self, text, enabled, guard=None):
        events = []
        app = SimpleNamespace(model=object(), finished=Mock(), show_saved_transcript=Mock(), asr_lock=threading.Lock())

        def save(*_):
            events.append("saved")
            return text, {"audio_seconds": 2, "transcribe_seconds": .2}

        def execute(command):
            events.append(command)
            return "Brought the browser forward"

        with patch("gui.save_transcript", side_effect=save), \
             patch("gui.execute_command", side_effect=execute), \
             patch("gui.GLib.idle_add", side_effect=lambda callback, *args: callback(*args)):
            Keety.convert(app, Path("test.wav"), enabled, command_guard=guard)
        return events, app

    def test_enabled_exact_match_saves_before_action(self):
        events, app = self.route("Open Chrome.", True)
        self.assertEqual(events, ["saved", "browser"])
        app.show_saved_transcript.assert_called_once()
        self.assertIn("Brought the browser", app.finished.call_args.args[1])

    def test_dictation_and_retry_mode_never_execute(self):
        events, _ = self.route("Open Chrome.", False)
        self.assertEqual(events, ["saved"])

    def test_unlisted_sentence_is_only_saved(self):
        events, app = self.route("I was going to open Chrome.", True)
        self.assertEqual(events, ["saved"])
        self.assertIn("No matching voice command", app.finished.call_args.args[1])

    def test_pausing_cancels_pending_action_but_saves_text(self):
        events, _ = self.route("Open Chrome.", True, guard=lambda: False)
        self.assertEqual(events, ["saved"])


if __name__ == "__main__":
    unittest.main()
