"""Small explicit speech-command vocabulary for the installed Hyprland desktop."""
import json
from pathlib import Path
import re
import subprocess
import time
import shutil

from command_catalog import GRAMMAR, SITES

BROWSER_CLASSES = {"chromium", "google-chrome", "google-chrome-stable", "chrome"}
MAIN_MONITOR = "DP-1"


def parse_command(text):
    normalized = " ".join(text.lower().split()).strip(" .!?")
    return GRAMMAR.get(normalized)


def browser_window(clients):
    # Match real browser windows, not Chrome-hosted Discord or other web apps.
    matches = [c for c in clients if c.get("class", "").lower() in BROWSER_CLASSES
               and re.fullmatch(r"0x[0-9a-fA-F]+", c.get("address", ""))]
    return min(matches, key=lambda c: c.get("focusHistoryID", 99999), default=None)


def run(argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip() or f"{argv[0]} failed")
    return result.stdout


def focus(window):
    address = window["address"]
    if not re.fullmatch(r"0x[0-9a-fA-F]+", address):
        raise ValueError("Invalid Hyprland window address")
    run(["hyprctl", "dispatch", f'hl.dsp.focus({{ window = "address:{address}" }})'])
    active = json.loads(run(["hyprctl", "activewindow", "-j"]))
    if active.get("address") != address:
        raise RuntimeError("Browser found, but Hyprland did not focus it")


def present_browser(window, fullscreen):
    move_to_main_screen(window)
    focus(window)
    if fullscreen:
        # Set an explicit state: repeating the command must never toggle it off.
        run(["hyprctl", "dispatch", "hl.dsp.window.fullscreen_state({ internal = 2, client = 2 })"])
        active = json.loads(run(["hyprctl", "activewindow", "-j"]))
        if active.get("address") != window["address"] or active.get("fullscreen") != 2:
            raise RuntimeError("Browser focused, but fullscreen was not confirmed")


def main_monitor(monitors):
    monitor = next((m for m in monitors if m.get("name") == MAIN_MONITOR and not m.get("disabled")), None)
    if monitor is None:
        raise RuntimeError(f"External screen {MAIN_MONITOR} is not connected")
    workspace = monitor.get("activeWorkspace", {}).get("id")
    if not isinstance(workspace, int) or workspace <= 0:
        raise RuntimeError("External screen has no usable active workspace")
    return monitor


def move_to_main_screen(window):
    monitor = main_monitor(json.loads(run(["hyprctl", "monitors", "-j"])))
    address = window["address"]
    if not re.fullmatch(r"0x[0-9a-fA-F]+", address):
        raise ValueError("Invalid Hyprland window address")
    workspace = monitor["activeWorkspace"]["id"]
    run(["hyprctl", "dispatch",
         f'hl.dsp.window.move({{ window = "address:{address}", workspace = "{workspace}", follow = false }})'])
    clients = json.loads(run(["hyprctl", "clients", "-j"]))
    moved = next((c for c in clients if c.get("address") == address), None)
    if moved is None or moved.get("monitor") != monitor["id"]:
        raise RuntimeError("Could not move the browser to the external screen")


def execute_command(command):
    if command.startswith("site:"):
        return present_site(command.removeprefix("site:"))
    if command not in ("browser", "browser_fullscreen"):
        raise ValueError("Unsupported voice command")
    fullscreen = command == "browser_fullscreen"
    # Check before launching anything: keep the laptop reserved for Keety.
    main_monitor(json.loads(run(["hyprctl", "monitors", "-j"])))
    window = browser_window(json.loads(run(["hyprctl", "clients", "-j"])))
    if window:
        present_browser(window, fullscreen)
        return "Brought the browser fullscreen" if fullscreen else "Brought the browser forward"
    candidates = [Path.home() / ".local/share/applications/chromium.desktop",
                  Path("/usr/share/applications/chromium.desktop"),
                  Path("/usr/share/applications/google-chrome.desktop")]
    desktop = next((p for p in candidates if p.is_file()), None)
    if not desktop:
        raise RuntimeError("No installed Chrome/Chromium application launcher found")
    run(["gio", "launch", str(desktop)])
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        window = browser_window(json.loads(run(["hyprctl", "clients", "-j"])))
        if window:
            present_browser(window, fullscreen)
            return "Opened the browser fullscreen" if fullscreen else "Opened the browser"
        time.sleep(0.15)
    raise RuntimeError("Launch requested, but no browser window appeared within 10 seconds")


def site_window(site, clients):
    matches = [c for c in clients if c.get("class") == site["class"]
               and re.fullmatch(r"0x[0-9a-fA-F]+", c.get("address", ""))]
    return min(matches, key=lambda c: c.get("focusHistoryID", 99999), default=None)


def present_site(key):
    if key not in SITES:
        raise ValueError("Unsupported website command")
    site = SITES[key]
    main_monitor(json.loads(run(["hyprctl", "monitors", "-j"])))
    window = site_window(site, json.loads(run(["hyprctl", "clients", "-j"])))
    if window:
        present_browser(window, fullscreen=True)
        return f"Brought {site['name']} fullscreen"
    browser = shutil.which("chromium")
    if not browser:
        raise RuntimeError("Chromium is not installed")
    # URL comes exclusively from the fixed registry. Preserve the normal profile
    # so the site uses the user's existing logins. No recognized text is executed.
    process = subprocess.Popen([browser, "--app=" + site["url"]],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        process.poll()  # reap the short-lived launcher when Chromium was running
        window = site_window(site, json.loads(run(["hyprctl", "clients", "-j"])))
        if window:
            present_browser(window, fullscreen=True)
            return f"Opened {site['name']} fullscreen"
        time.sleep(0.15)
    raise RuntimeError(f"Launch requested, but no {site['name']} window appeared within 10 seconds")
