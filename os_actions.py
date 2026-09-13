"""Small explicit speech-command vocabulary for the installed Hyprland desktop."""
import json
from pathlib import Path
import re
import subprocess
import time
from browser_connection import connection

from command_catalog import APPS, GRAMMAR, SITES
from intent_matching import normalize

BROWSER_CLASSES = {"chromium", "google-chrome", "google-chrome-stable", "chrome"}
MAIN_MONITOR = "DP-1"
TERMINAL_CLASSES = {"foot", "footclient", "alacritty", "kitty", "org.wezfurlong.wezterm", "com.mitchellh.ghostty"}
TERMINAL_CLOSE_INTENTS = {"close:terminal", "close:terminal_current"}


def parse_command(text):
    return GRAMMAR.get(normalize(text))


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
    normal_browser = browser_window([window]) is not None
    if fullscreen or (normal_browser and (window.get("fullscreen", 0) >= 2 or window.get("fullscreenClient", 0) >= 2)):
        # Normal browsers keep their tabs/address bar; standalone apps can fill the screen.
        state = 1 if normal_browser else 2
        address = window["address"]
        run(["hyprctl", "dispatch", f'hl.dsp.window.fullscreen_state({{ internal = {state}, client = {state}, '
             f'action = "set", window = "address:{address}" }})'])
        active = json.loads(run(["hyprctl", "activewindow", "-j"]))
        if active.get("address") != address or active.get("fullscreen") != state or active.get("fullscreenClient") != state:
            raise RuntimeError("Window focused, but its display mode was not confirmed")


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
    if command == "terminal:new":
        return open_terminal()
    if command in APPS:
        return present_app(command)
    if command.startswith("maximize:"):
        return maximize_app(command.removeprefix("maximize:"))
    if command.startswith("close:"):
        return close_app(command.removeprefix("close:"))
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
        return "Brought the browser maximized" if fullscreen else "Brought the browser forward"
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
            return "Opened the browser maximized" if fullscreen else "Opened the browser"
        time.sleep(0.15)
    raise RuntimeError("Launch requested, but no browser window appeared within 10 seconds")


def capture_window_context():
    try:
        return {"active": json.loads(run(["hyprctl", "activewindow", "-j"])),
                "clients": json.loads(run(["hyprctl", "clients", "-j"]))}
    except Exception:
        return None


def window_target(context):
    target = context.get("active", {}) if context else {}
    if not target.get("mapped", True) or not re.fullmatch(r"0x[0-9a-fA-F]+", target.get("address", "")):
        raise RuntimeError("No focused window was captured when recording started")
    return dict(target)


def maximize_current_window(target):
    target = window_target({"active": target or {}})
    clients = json.loads(run(["hyprctl", "clients", "-j"]))
    current = next((c for c in clients if c.get("address") == target["address"]), None)
    if current is None or any(current.get(k) != target.get(k) for k in ("pid", "class", "stableId")):
        raise RuntimeError("That window closed or changed. No other window was maximized.")
    address = target["address"]
    focus(current)
    run(["hyprctl", "dispatch", 'hl.dsp.window.fullscreen_state({ internal = 1, client = 1, '
         f'action = "set", window = "address:{address}" }})'])
    maximized = next((c for c in json.loads(run(["hyprctl", "clients", "-j"]))
                      if c.get("address") == address), None)
    if (maximized is None or maximized.get("fullscreen") != 1
            or maximized.get("fullscreenClient") != 1 or maximized.get("monitor") != current.get("monitor")):
        raise RuntimeError("Could not confirm the window was maximized on its current screen")
    return "Maximized this window"


def move_other_screen(target):
    target = window_target({"active": target})
    clients = json.loads(run(["hyprctl", "clients", "-j"]))
    current = next((c for c in clients if c.get("address") == target["address"]), None)
    if current is None or any(current.get(k) != target.get(k) for k in ("pid", "class", "stableId")):
        raise RuntimeError("That window closed or changed. No other window was moved.")
    monitors = sorted((m for m in json.loads(run(["hyprctl", "monitors", "-j"]))
                       if not m.get("disabled")), key=lambda m: m["id"])
    source = next((i for i, m in enumerate(monitors) if m["id"] == current.get("monitor")), None)
    if len(monitors) < 2 or source is None:
        raise RuntimeError("No other connected screen is available")
    destination = monitors[(source + 1) % len(monitors)]
    workspace = destination.get("activeWorkspace", {}).get("id")
    if type(workspace) is not int or workspace <= 0:
        raise RuntimeError("The other screen has no usable active workspace")
    address = target["address"]
    run(["hyprctl", "dispatch", f'hl.dsp.window.move({{ window = "address:{address}", workspace = "{workspace}", follow = true }})'])
    run(["hyprctl", "dispatch", f'hl.dsp.focus({{ window = "address:{address}" }})'])
    moved = next((c for c in json.loads(run(["hyprctl", "clients", "-j"])) if c.get("address") == address), None)
    if moved is None or moved.get("monitor") != destination["id"]:
        raise RuntimeError("Could not confirm the window moved to the other screen")
    return f"Moved window to {destination['name']}"


def is_terminal(window):
    return (window.get("class", "").lower() in TERMINAL_CLASSES
            and window.get("mapped", True)
            and re.fullmatch(r"0x[0-9a-fA-F]+", window.get("address", "")))


def terminal_close_target(intent, context):
    if intent not in TERMINAL_CLOSE_INTENTS:
        raise ValueError("Unsupported terminal command")
    if context is None:
        raise RuntimeError("Could not identify the terminal when recording started. Try again.")
    if intent == "close:terminal_current":
        target = context["active"]
        if not is_terminal(target):
            raise RuntimeError("The window you were in was not a terminal. No window was closed.")
    else:
        target = min((c for c in context["clients"] if is_terminal(c)),
                     key=lambda c: c.get("focusHistoryID", 99999), default=None)
        if target is None:
            raise RuntimeError("No open terminal window")
    return dict(target)


def close_terminal(target):
    if not is_terminal(target):
        raise ValueError("Invalid terminal target")
    clients = json.loads(run(["hyprctl", "clients", "-j"]))
    current = next((c for c in clients if c.get("address") == target["address"]), None)
    if current is None:
        return "That terminal has already closed"
    if not is_terminal(current) or any(current.get(k) != target.get(k) for k in ("pid", "class", "stableId")):
        raise RuntimeError("The terminal changed. No window was closed; try again.")
    run(["hyprctl", "dispatch", f'hl.dsp.window.close({{ window = "address:{target["address"]}" }})'])
    return "Asked the selected terminal to close. Respond to any confirmation it shows."


def open_terminal():
    main_monitor(json.loads(run(["hyprctl", "monitors", "-j"])))
    before = {c["address"] for c in json.loads(run(["hyprctl", "clients", "-j"]))}
    # Use the configured desktop terminal, with no speech-derived shell arguments.
    run(["hyprctl", "dispatch", 'hl.dsp.exec_cmd("omarchy launch terminal")'])
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        clients = json.loads(run(["hyprctl", "clients", "-j"]))
        window = next((c for c in clients
                       if c.get("address") not in before
                       and c.get("class", "").lower() in TERMINAL_CLASSES
                       and c.get("mapped", True)
                       and re.fullmatch(r"0x[0-9a-fA-F]+", c.get("address", ""))), None)
        if window:
            move_to_main_screen(window)
            focus(window)
            return "Opened a new terminal"
        time.sleep(0.1)
    raise RuntimeError("Launch requested, but no new terminal window appeared within 10 seconds")


def app_window(key, clients):
    classes = APPS[key]["classes"]
    matches = [c for c in clients if c.get("class") in classes
               and c.get("mapped", True)
               and re.fullmatch(r"0x[0-9a-fA-F]+", c.get("address", ""))]
    return min(matches, key=lambda c: c.get("focusHistoryID", 99999), default=None)


def present_app(key):
    app = APPS[key]
    name = app["name"]
    main_monitor(json.loads(run(["hyprctl", "monitors", "-j"])))
    window = app_window(key, json.loads(run(["hyprctl", "clients", "-j"])))
    if window:
        present_browser(window, fullscreen=True)
        return f"Brought {name} forward"
    candidates = [directory / filename
                  for directory in (Path.home() / ".local/share/applications", Path("/usr/share/applications"))
                  for filename in app["desktop_files"]]
    desktop = next((p for p in candidates if p.is_file()), None)
    if desktop is None:
        raise RuntimeError(f"No installed {name} application launcher found")
    run(["gio", "launch", str(desktop)])
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        window = app_window(key, json.loads(run(["hyprctl", "clients", "-j"])))
        if window:
            present_browser(window, fullscreen=True)
            return f"Opened {name}"
        time.sleep(0.15)
    raise RuntimeError(f"Launch requested, but no {name} window appeared within 15 seconds")


def maximize_app(key):
    if key != "browser" and key not in APPS:
        raise ValueError("Unsupported app to maximize")
    name = "Chrome" if key == "browser" else APPS[key]["name"]
    clients = json.loads(run(["hyprctl", "clients", "-j"]))
    window = browser_window(clients) if key == "browser" else app_window(key, clients)
    if window is None:
        return f"No open {name} window"
    move_to_main_screen(window)
    focus(window)
    address = window["address"]
    # Set both compositor and client to maximized, including when leaving fullscreen.
    run(["hyprctl", "dispatch", 'hl.dsp.window.fullscreen_state({ internal = 1, client = 1, '
         f'action = "set", window = "address:{address}" }})'])
    clients = json.loads(run(["hyprctl", "clients", "-j"]))
    maximized = next((c for c in clients if c.get("address") == address), None)
    if maximized is None or maximized.get("fullscreen") != 1 or maximized.get("fullscreenClient") != 1:
        raise RuntimeError(f"Could not confirm that {name} was maximized")
    return f"Maximized {name} window"


def close_app(key):
    if key != "browser" and key not in APPS:
        raise ValueError("Unsupported app to close")
    name = "Chrome" if key == "browser" else APPS[key]["name"]
    clients = json.loads(run(["hyprctl", "clients", "-j"]))
    window = browser_window(clients) if key == "browser" else app_window(key, clients)
    if window is None:
        return f"No open {name} window"
    address = window["address"]  # validated by the exact-class selector
    run(["hyprctl", "dispatch", f'hl.dsp.window.close({{ window = "address:{address}" }})'])
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        clients = json.loads(run(["hyprctl", "clients", "-j"]))
        if not any(c.get("address") == address and c.get("mapped", True) for c in clients):
            return f"Closed {name} window"
        time.sleep(0.1)
    return f"Asked {name} to close; its window is still open. Check it for a confirmation."


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
