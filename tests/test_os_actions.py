import json
import unittest
from unittest.mock import patch

from os_actions import parse_command, browser_window, execute_command, move_to_main_screen, main_monitor

MONITORS = '[{"name":"eDP-1","id":0,"activeWorkspace":{"id":1}},{"name":"DP-1","id":1,"activeWorkspace":{"id":7}}]'


class CommandTests(unittest.TestCase):
    def test_requested_phrases(self):
        for text in ["Open Chrome.", "open Chromium.",
                     "Open Google Chrome", "focus chrome", "  OPEN   CHROME!  "]:
            with self.subTest(text=text):
                self.assertEqual(parse_command(text), "browser")

    def test_bring_up_requests_fullscreen(self):
        for text in ["Bring up Chrome!", "bring up chromium", "bring up Google Chrome."]:
            self.assertEqual(parse_command(text), "browser_fullscreen")

    def test_fullscreen_is_set_not_toggled(self):
        for current_state in (0, 2):
            responses = [MONITORS, json.dumps([{"class": "chromium", "address": "0x123", "fullscreen": current_state}]),
                         'ok', '{"address":"0x123"}', 'ok', '{"address":"0x123","fullscreen":2}']
            with patch("os_actions.run", side_effect=responses) as run, patch("os_actions.move_to_main_screen") as move:
                self.assertEqual(execute_command("browser_fullscreen"), "Brought the browser fullscreen")
                move.assert_called_once()
                self.assertIn("internal = 2, client = 2", run.call_args_list[4].args[0][2])

    def test_dictation_is_not_executed(self):
        for text in ["Don't open Chrome", "I said open Chrome", "open chrome; rm -rf /",
                     "open chrome and send a message", "open terminal", "",
                     "please open chrome", "open chrome please"]:
            with self.subTest(text=text):
                self.assertIsNone(parse_command(text))

    def test_excludes_browser_webapps_and_bad_addresses(self):
        self.assertIsNone(browser_window([
            {"class": "chrome-discord.com__channels_@me-Default", "address": "0x123"},
            {"class": "chromium", "address": '0x123\"'}]))

    def test_focuses_existing_browser_without_launching(self):
        responses = [MONITORS, '[{"class":"chromium","address":"0x123"}]', 'ok', '{"address":"0x123"}']
        with patch("os_actions.run", side_effect=responses) as run, patch("os_actions.move_to_main_screen"):
            self.assertEqual(execute_command("browser"), "Brought the browser forward")
            self.assertEqual(run.call_count, 4)
            self.assertFalse(any(c.args[0][0] == "gio" for c in run.call_args_list))

    def test_targets_external_active_workspace(self):
        with patch("os_actions.run", side_effect=[MONITORS, 'ok', '[{"address":"0x123","monitor":1}]']) as run:
            move_to_main_screen({"address": "0x123"})
            self.assertIn('workspace = "7"', run.call_args_list[1].args[0][2])
            self.assertIn('follow = false', run.call_args_list[1].args[0][2])

    def test_missing_external_stops_before_launching(self):
        with patch("os_actions.run", return_value='[{"name":"eDP-1","id":0,"activeWorkspace":{"id":1}}]') as run:
            with self.assertRaisesRegex(RuntimeError, "not connected"):
                execute_command("browser")
            run.assert_called_once_with(["hyprctl", "monitors", "-j"])

    def test_no_usable_external_workspace(self):
        with self.assertRaisesRegex(RuntimeError, "no usable"):
            main_monitor([{"name": "DP-1", "id": 1, "activeWorkspace": {"id": -1}}])


if __name__ == "__main__":
    unittest.main()
