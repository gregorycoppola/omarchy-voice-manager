import json
import unittest
from subprocess import CompletedProcess
from unittest.mock import patch

from os_actions import parse_command, browser_window, execute_command, move_to_main_screen, main_monitor
from command_catalog import SITES

MONITORS = '[{"name":"eDP-1","id":0,"activeWorkspace":{"id":1}},{"name":"DP-1","id":1,"activeWorkspace":{"id":7}}]'


class CommandTests(unittest.TestCase):
    def test_window_phrases_are_exact_commands(self):
        for phrase in ["Show all windows.", " SHOW  ALL OPEN WINDOWS! "]:
            self.assertEqual(parse_command(phrase), "windows")
        self.assertIsNone(parse_command("do not show all windows"))

    def test_window_list_includes_other_workspaces_and_focuses_exact_choice(self):
        clients = [
            {"mapped": True, "address": "0x1", "title": "Same title", "workspace": {"name": "1"}},
            {"mapped": True, "hidden": True, "address": "0x2", "title": "Same title", "workspace": {"name": "9"}},
            {"mapped": False, "address": "0x3", "title": "Unmapped"},
            {"mapped": True, "address": '0x4\"', "title": "Invalid"},
        ]
        with patch("os_actions.run", side_effect=[json.dumps(clients), "ok", '{"address":"0x2"}']) as run, \
             patch("os_actions.subprocess.run", return_value=CompletedProcess([], 0, "2. Same title — Workspace 9\n", "")) as menu:
            self.assertEqual(execute_command("windows"), "Brought selected window forward")
            self.assertEqual(menu.call_args.kwargs["input"], "1. Same title — Workspace 1\n2. Same title — Workspace 9\n")
            self.assertIn('address:0x2', run.call_args_list[1].args[0][2])

    def test_window_list_cancel_does_not_change_focus(self):
        clients = [{"mapped": True, "address": "0x1", "title": "Window"}]
        with patch("os_actions.run", return_value=json.dumps(clients)) as run, \
             patch("os_actions.subprocess.run", return_value=CompletedProcess([], 1, "", "")):
            self.assertEqual(execute_command("windows"), "Window list closed")
            run.assert_called_once()

    def test_empty_window_list_does_not_open_menu(self):
        with patch("os_actions.run", return_value="[]"), patch("os_actions.subprocess.run") as menu:
            self.assertEqual(execute_command("windows"), "No open windows")
            menu.assert_not_called()

    def test_requested_phrases(self):
        for text in ["Open Chrome.", "open Chromium.",
                     "Open Google Chrome", "focus chrome", "  OPEN   CHROME!  "]:
            with self.subTest(text=text):
                self.assertEqual(parse_command(text), "browser")

    def test_bring_up_requests_fullscreen(self):
        for text in ["Bring up Chrome!", "bring up chromium", "bring up Google Chrome."]:
            self.assertEqual(parse_command(text), "browser_fullscreen")

    def test_fixed_website_vocabulary(self):
        for phrase, site in [("Bring up Gmail.", "gmail"), ("open g mail", "gmail"),
                             ("bring up GitHub", "github"), ("OPEN  GIT HUB!", "github")]:
            self.assertEqual(parse_command(phrase), "site:" + site)
        for phrase in ["open gmail and github", "do not open github", "open github.com",
                       "bring up example.com", "open gmail please"]:
            self.assertIsNone(parse_command(phrase))

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

    def test_site_uses_browser_tab_then_fullscreens_selected_browser(self):
        window = {"class": "chromium", "address": "0x123"}
        with patch("os_actions.run", side_effect=[MONITORS, json.dumps(window)]), \
             patch("os_actions.execute_command") as ensure, \
             patch("os_actions.connection.bring_up", return_value={"reused": True}) as tabs, \
             patch("os_actions.present_browser") as present:
            from os_actions import present_site
            self.assertEqual(present_site("github"), "Reused GitHub tab")
            ensure.assert_called_once_with("browser")
            tabs.assert_called_once_with(SITES["github"])
            present.assert_called_once_with(window, fullscreen=True)

    def test_arbitrary_website_id_rejected_before_os_access(self):
        with patch("os_actions.run") as run:
            with self.assertRaises(ValueError):
                execute_command("site:https://example.com")
            run.assert_not_called()

    def test_site_requires_external_before_launch(self):
        with patch("os_actions.run", return_value="[]"), patch("os_actions.subprocess.Popen") as launch:
            with self.assertRaisesRegex(RuntimeError, "not connected"):
                execute_command("site:gmail")
            launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
