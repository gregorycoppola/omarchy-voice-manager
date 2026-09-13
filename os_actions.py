"""Small explicit speech-command vocabulary for the installed Hyprland desktop."""
import json
from pathlib import Path
import re
import subprocess
import time

BROWSER_CLASSES = {"chromium", "google-chrome", "google-chrome-stable", "chrome"}
GRAMMAR = {
    "open chrome": "browser",
    "bring up chrome": "browser_fullscreen",
    "launch chrome": "browser",
    "focus chrome": "browser",
    "switch to chrome": "browser",
    "open chromium": "browser",
    "bring up chromium": "browser_fullscreen",
    "open google chrome": "browser",
    "bring up google chrome": "browser_fullscreen",
}


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
    focus(window)
    if fullscreen:
        # Set an explicit state: repeating the command must never toggle it off.
        run(["hyprctl", "dispatch", "hl.dsp.window.fullscreen_state({ internal = 2, client = 2 })"])
        active = json.loads(run(["hyprctl", "activewindow", "-j"]))
        if active.get("address") != window["address"] or active.get("fullscreen") != 2:
            raise RuntimeError("Browser focused, but fullscreen was not confirmed")


def execute_command(command):
    if command not in ("browser", "browser_fullscreen"):
        raise ValueError("Unsupported voice command")
    fullscreen = command == "browser_fullscreen"
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
