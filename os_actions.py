"""Small explicit speech-command vocabulary for the installed Hyprland desktop."""
import json
from pathlib import Path
import re
import subprocess
import time
from browser_connection import connection

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
    if command == "discord":
        return present_discord()
    if command == "windows":
        return show_windows()
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


def discord_window(clients):
    classes = {"discord", "Discord", "chrome-discord.com__channels_@me-Default"}
    matches = [c for c in clients if c.get("class") in classes
               and re.fullmatch(r"0x[0-9a-fA-F]+", c.get("address", ""))]
    return min(matches, key=lambda c: c.get("focusHistoryID", 99999), default=None)


def present_discord():
    main_monitor(json.loads(run(["hyprctl", "monitors", "-j"])))
    window = discord_window(json.loads(run(["hyprctl", "clients", "-j"])))
    if window:
        present_browser(window, fullscreen=True)
        return "Brought Discord forward"
    candidates = [Path.home() / ".local/share/applications/Discord.desktop",
                  Path.home() / ".local/share/applications/discord.desktop",
                  Path("/usr/share/applications/discord.desktop")]
    desktop = next((p for p in candidates if p.is_file()), None)
    if desktop is None:
        raise RuntimeError("No installed Discord application launcher found")
    run(["gio", "launch", str(desktop)])
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        window = discord_window(json.loads(run(["hyprctl", "clients", "-j"])))
        if window:
            present_browser(window, fullscreen=True)
            return "Opened Discord"
        time.sleep(0.15)
    raise RuntimeError("Launch requested, but no Discord window appeared within 15 seconds")


def show_windows():
    clients = json.loads(run(["hyprctl", "clients", "-j"]))
    choices = {}
    for client in sorted(clients, key=lambda c: c.get("focusHistoryID", 99999)):
        address = client.get("address", "")
        if not client.get("mapped") or not re.fullmatch(r"0x[0-9a-fA-F]+", address):
            continue
        title = " ".join((client.get("title") or client.get("class") or "Untitled").split())
        workspace = " ".join(str(client.get("workspace", {}).get("name", "?")).split())
        label = f"{len(choices) + 1}. {title} — Workspace {workspace}"
        choices[label] = address
    if not choices:
        return "No open windows"
    # Wait for the user's selection, without the short timeout used for OS calls.
    # Supply titles through stdin so even '--' and shell text remain plain data.
    selection = subprocess.run(["omarchy", "menu", "select", "Open windows"],
                               input="\n".join(choices) + "\n",
                               capture_output=True, text=True)
    if selection.returncode == 1 and not selection.stdout.strip() and not selection.stderr.strip():
        return "Window list closed"
    if selection.returncode:
        raise RuntimeError(selection.stderr.strip() or "Could not show open windows")
    address = choices.get(selection.stdout.strip())
    if address is None:
        raise RuntimeError("Window selection was not recognized")
    run(["hyprctl", "dispatch", f'hl.dsp.focus({{ window = "address:{address}" }})'])
    active = json.loads(run(["hyprctl", "activewindow", "-j"]))
    if active.get("address") != address:
        raise RuntimeError("Selected window could not be focused; it may have closed")
    return "Brought selected window forward"


def present_site(key):
    if key not in SITES:
        raise ValueError("Unsupported website command")
    site = SITES[key]
    main_monitor(json.loads(run(["hyprctl", "monitors", "-j"])))
    # Ensure the regular browser exists before connecting to its extension.
    execute_command("browser")
    selected = connection.bring_up(site)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        active = json.loads(run(["hyprctl", "activewindow", "-j"]))
        if browser_window([active]):
            present_browser(active, fullscreen=True)
            return f"{'Reused' if selected['reused'] else 'Opened'} {site['name']} tab"
        time.sleep(0.05)
    raise RuntimeError("Tab selected, but the browser window did not become active")
