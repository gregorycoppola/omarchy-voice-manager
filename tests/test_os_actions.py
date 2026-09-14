import json
import unittest
from subprocess import CompletedProcess
from unittest.mock import patch

from os_actions import parse_command, browser_window, execute_command, move_to_main_screen, main_monitor
from command_catalog import SITES

MONITORS = '[{"name":"eDP-1","id":0,"activeWorkspace":{"id":1}},{"name":"DP-1","id":1,"activeWorkspace":{"id":7}}]'


class CommandTests(unittest.TestCase):
    def test_discord_phrases_are_exact(self):
        self.assertEqual(parse_command("Bring up Discord!"), "discord")
        self.assertEqual(parse_command("open discord"), "discord")
        self.assertIsNone(parse_command("do not bring up discord"))
        self.assertIsNone(parse_command("open discord and send a message"))

    def test_discord_reuses_app_window_without_launch(self):
        window = {"class": "chrome-discord.com__channels_@me-Default", "address": "0x123"}
        with patch("os_actions.run", side_effect=[MONITORS, json.dumps([window])]) as run, \
             patch("os_actions.present_browser") as present:
            self.assertEqual(execute_command("discord"), "Brought Discord forward")
            present.assert_called_once_with(window, fullscreen=True)
            self.assertEqual(run.call_count, 2)

    def test_discord_launches_installed_desktop_then_focuses(self):
        window = {"class": "discord", "address": "0x123"}
        with patch("os_actions.run", side_effect=[MONITORS, "[]", "ok", json.dumps([window])]) as run, \
             patch("os_actions.Path.is_file", return_value=True), \
             patch("os_actions.present_browser") as present:
            self.assertEqual(execute_command("discord"), "Opened Discord")
            self.assertEqual(run.call_args_list[2].args[0][:2], ["gio", "launch"])
            present.assert_called_once_with(window, fullscreen=True)

    def test_discord_ignores_browser_title_and_requires_main_monitor(self):
        from os_actions import app_window
        self.assertIsNone(app_window("discord", [{"class":"chromium", "title":"Discord", "address":"0x123"}]))
        with patch("os_actions.run", return_value="[]") as run:
            with self.assertRaisesRegex(RuntimeError, "not connected"):
                execute_command("discord")
            self.assertEqual(run.call_count, 1)

    def test_x_and_close_vocabulary(self):
        for phrase in ["Open X!", "open twitter", "bring up x", "bring up Twitter"]:
            self.assertEqual(parse_command(phrase), "x")
        for phrase, intent in [("close x", "close:x"), ("Close Twitter!", "close:x"),
                               ("close discord", "close:discord"), ("close chromium", "close:browser")]:
            self.assertEqual(parse_command(phrase), intent)
        for phrase in ["close everything", "do not close x", "close discord and chrome"]:
            self.assertIsNone(parse_command(phrase))

    def test_x_reuses_installed_app_not_browser_title(self):
        clients = [{"class": "chromium", "title": "X", "address": "0x1"},
                   {"class": "chrome-x.com__-Default", "address": "0x2"}]
        with patch("os_actions.run", side_effect=[MONITORS, json.dumps(clients)]), \
             patch("os_actions.present_browser") as present:
            self.assertEqual(execute_command("x"), "Brought X (Twitter) forward")
            present.assert_called_once_with(clients[1], fullscreen=True)

    def test_x_launches_installed_desktop(self):
        window = {"class": "chrome-x.com__-Default", "address": "0x2"}
        with patch("os_actions.run", side_effect=[MONITORS, "[]", "ok", json.dumps([window])]) as run, \
             patch("os_actions.Path.is_file", return_value=True), patch("os_actions.present_browser"):
            self.assertEqual(execute_command("x"), "Opened X (Twitter)")
            self.assertTrue(run.call_args_list[2].args[0][2].endswith("/X.desktop"))

    def test_close_targets_one_recent_app_window_without_focus_or_launch(self):
        clients = [{"class": "chromium", "title": "Discord", "address": "0x1", "focusHistoryID": 0},
                   {"class": "discord", "address": "0x2", "focusHistoryID": 4},
                   {"class": "discord", "address": "0x3", "focusHistoryID": 1}]
        with patch("os_actions.run", side_effect=[json.dumps(clients), "ok", json.dumps(clients[:2])]) as run:
            self.assertEqual(execute_command("close:discord"), "Closed Discord window")
            self.assertEqual(run.call_args_list[1].args[0],
                             ["hyprctl", "dispatch", 'hl.dsp.window.close({ window = "address:0x3" })'])
            self.assertEqual(run.call_count, 3)

    def test_close_x_supports_twitter_app_class(self):
        for app_class in ["chrome-x.com__-Default", "chrome-twitter.com__-Default"]:
            with patch("os_actions.run", side_effect=[json.dumps([{"class": app_class, "address": "0x2"}]), "ok", "[]"]):
                self.assertEqual(execute_command("close:x"), "Closed X (Twitter) window")

    def test_close_missing_or_invalid_target_never_closes_unrelated_window(self):
        clients = [{"class": "chromium", "title": "Discord", "address": "0x1"},
                   {"class": "discord", "address": '0x2"'},
                   {"class": "discord", "address": "0x3", "mapped": False}]
        with patch("os_actions.run", return_value=json.dumps(clients)) as run:
            self.assertEqual(execute_command("close:discord"), "No open Discord window")
            run.assert_called_once()
        with patch("os_actions.run") as run:
            with self.assertRaises(ValueError):
                execute_command("close:arbitrary")
            run.assert_not_called()

    def test_close_chrome_does_not_close_webapps(self):
        clients = [{"class": "chrome-x.com__-Default", "address": "0x1"},
                   {"class": "chromium", "address": "0x2"}]
        with patch("os_actions.run", side_effect=[json.dumps(clients), "ok", json.dumps(clients[:1])]) as run:
            self.assertEqual(execute_command("close:browser"), "Closed Chrome window")
            self.assertIn('address:0x2', run.call_args_list[1].args[0][2])

    def test_close_leaves_app_confirmation_to_user(self):
        clients = [{"class": "discord", "address": "0x2"}]
        with patch("os_actions.run", side_effect=[json.dumps(clients), "ok"]) as run, \
             patch("os_actions.time.monotonic", side_effect=[0, 3]):
            self.assertIn("window is still open", execute_command("close:discord"))
            self.assertEqual(run.call_count, 2)

    def test_maximize_vocabulary(self):
        for phrase, intent in [("Maximize Chromium!", "maximize:browser"),
                               ("maximize chrome", "maximize:browser"),
                               ("maximize google chrome", "maximize:browser"),
                               ("maximize discord", "maximize:discord"),
                               ("maximize x", "maximize:x"), ("maximize twitter", "maximize:x")]:
            self.assertEqual(parse_command(phrase), intent)
        self.assertIsNone(parse_command("do not maximize chromium"))

    def test_maximize_sets_one_exact_window_and_both_states(self):
        for key, app_class in [("browser", "chromium"), ("discord", "discord"), ("x", "chrome-x.com__-Default")]:
            window = {"class": app_class, "address": "0x2", "fullscreen": 2}
            with patch("os_actions.run", return_value=json.dumps([window])), \
                 patch("os_actions.move_to_main_screen") as move, patch("os_actions.maximize_foreground") as present:
                self.assertIn("Maximized", execute_command("maximize:" + key))
                move.assert_not_called()
                present.assert_called_once_with(window)

    def test_maximize_missing_window_does_not_launch(self):
        with patch("os_actions.run", return_value="[]") as run:
            self.assertEqual(execute_command("maximize:browser"), "No open Chrome window")
            run.assert_called_once()
        with patch("os_actions.run") as run:
            with self.assertRaises(ValueError):
                execute_command("maximize:arbitrary")
            run.assert_not_called()

    def test_maximize_reports_failed_confirmation(self):
        window = {"class": "chromium", "address": "0x2"}
        with patch("os_actions.run", return_value=json.dumps([window])), \
             patch("os_actions.move_to_main_screen"), \
             patch("os_actions.maximize_foreground", side_effect=RuntimeError("Could not confirm")):
            with self.assertRaisesRegex(RuntimeError, "confirm"):
                execute_command("maximize:browser")

    def test_new_terminal_phrases(self):
        for phrase in ["Open a new terminal.", "open a terminal", "open terminal", "open new terminal"]:
            self.assertEqual(parse_command(phrase), "terminal:new")
        self.assertIsNone(parse_command("open a terminal and run ls"))

    def test_terminal_always_launches_and_targets_only_new_terminal(self):
        old = {"class": "foot", "address": "0x1"}
        new = {"class": "foot", "address": "0x2"}
        unrelated = {"class": "chromium", "address": "0x3"}
        with patch("os_actions.run", side_effect=[MONITORS, json.dumps([old]), "ok", json.dumps([old, unrelated, new])]) as run, \
             patch("os_actions.move_to_main_screen") as move, patch("os_actions.present_new_terminal") as present:
            self.assertEqual(execute_command("terminal:new"), "Opened a new terminal")
            self.assertEqual(run.call_args_list[2].args[0], ["hyprctl", "dispatch", 'hl.dsp.exec_cmd("omarchy launch terminal")'])
            move.assert_called_once_with(new)
            present.assert_called_once_with(new)

    def test_terminal_missing_monitor_does_not_launch(self):
        with patch("os_actions.run", return_value="[]") as run:
            with self.assertRaisesRegex(RuntimeError, "not connected"):
                execute_command("terminal:new")
            run.assert_called_once()

    def test_terminal_reports_launch_timeout(self):
        with patch("os_actions.run", side_effect=[MONITORS, "[]", "ok"]), \
             patch("os_actions.time.monotonic", side_effect=[0, 11]):
            with self.assertRaisesRegex(RuntimeError, "no new terminal"):
                execute_command("terminal:new")

    def test_window_phrases_are_exact_commands(self):
        for phrase in ["Show all windows.", " SHOW  ALL OPEN WINDOWS! ", "Show all open window."]:
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

    def test_browser_maximizes_with_tabs_instead_of_fullscreen(self):
        for command in ('browser', 'browser_fullscreen'):
            window = {"class": "chromium", "address": "0x123"}
            with patch("os_actions.run", side_effect=[MONITORS, json.dumps([window])]), \
                 patch("os_actions.move_to_main_screen") as move, patch("os_actions.maximize_foreground") as present:
                execute_command(command)
                move.assert_called_once_with(window)
                present.assert_called_once_with(window)

    def test_open_browser_restores_tabs_from_fullscreen(self):
        from os_actions import present_browser
        window = {"class": "chromium", "address": "0x123", "fullscreen": 2}
        with patch("os_actions.move_to_main_screen"), patch("os_actions.maximize_foreground") as present:
            present_browser(window, fullscreen=False)
            present.assert_called_once_with(window)

    def test_standalone_apps_use_same_foreground_policy(self):
        from os_actions import present_browser
        window = {"class": "discord", "address": "0x123"}
        with patch("os_actions.move_to_main_screen"), patch("os_actions.maximize_foreground") as present:
            present_browser(window, fullscreen=True)
            present.assert_called_once_with(window)

    def test_dictation_is_not_executed(self):
        for text in ["Don't open Chrome", "I said open Chrome", "open chrome; rm -rf /",
                     "open chrome and send a message", "open a terminal and run ls", "",
                     "please open chrome", "open chrome please"]:
            with self.subTest(text=text):
                self.assertIsNone(parse_command(text))

    def test_excludes_browser_webapps_and_bad_addresses(self):
        self.assertIsNone(browser_window([
            {"class": "chrome-discord.com__channels_@me-Default", "address": "0x123"},
            {"class": "chromium", "address": '0x123\"'}]))

    def test_focuses_existing_browser_without_launching(self):
        responses = [MONITORS, '[{"class":"chromium","address":"0x123"}]']
        with patch("os_actions.run", side_effect=responses) as run, patch("os_actions.move_to_main_screen"), \
             patch("os_actions.maximize_foreground") as present:
            self.assertEqual(execute_command("browser"), "Brought the browser forward")
            self.assertEqual(run.call_count, 2)
            present.assert_called_once()

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
