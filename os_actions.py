"""Small explicit speech-command vocabulary for the installed Hyprland desktop."""
import json
import math
from pathlib import Path
import re
import subprocess
import threading
import time
from browser_connection import connection

from command_catalog import APPS, GRAMMAR, SITES, TERMINAL_CLASSES
from intent_matching import normalize

BROWSER_CLASSES = {"chromium", "google-chrome", "google-chrome-stable", "chrome"}
MAIN_MONITOR = "DP-1"
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


def launch_desktop(desktop):
    # A launched app can inherit gio's output handles and keep them open for
    # its entire lifetime. Never wait for captured output to reach EOF here.
    process = subprocess.Popen(['gio', 'launch', str(desktop)],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    threading.Thread(target=process.wait, daemon=True).start()
    return process


def focus(window):
    address = window["address"]
    if not re.fullmatch(r"0x[0-9a-fA-F]+", address):
        raise ValueError("Invalid Hyprland window address")
    run(["hyprctl", "dispatch", f'hl.dsp.focus({{ window = "address:{address}" }})'])
    active = json.loads(run(["hyprctl", "activewindow", "-j"]))
    if active.get("address") != address:
        raise RuntimeError("Browser found, but Hyprland did not focus it")


def present_browser(window, fullscreen):
    # Retain the legacy argument for existing callers/aliases. All opening
    # paths now share the same maximized, explicitly raised presentation.
    move_to_main_screen(window)
    maximize_foreground(window)


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
    launcher = launch_desktop(desktop)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        window = browser_window(json.loads(run(["hyprctl", "clients", "-j"])))
        if window:
            present_browser(window, fullscreen)
            return "Opened the browser maximized" if fullscreen else "Opened the browser"
        if launcher.poll() not in (None, 0):
            raise RuntimeError('Chrome launcher failed before a browser window appeared')
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


def equal_grid(count, monitor):
    """Equal logical-pixel rectangles, with room for the panel and window borders."""
    if count < 1:
        return []
    width, height = monitor["width"], monitor["height"]
    if monitor.get("transform", 0) % 2:
        width, height = height, width
    scale = monitor.get("scale", 1)
    left, top, right, bottom = monitor.get("reserved", [0, 0, 0, 0])
    width, height = int(width / scale) - left - right, int(height / scale) - top - bottom
    columns = math.ceil(math.sqrt(count))
    rows = math.ceil(count / columns)
    if height > width:
        columns, rows = rows, columns
    gap = 12
    w, h = (width - gap * (columns + 1)) // columns, (height - gap * (rows + 1)) // rows
    if w < 100 or h < 80:
        raise RuntimeError("Too many windows to fit an equal grid on this screen")
    return [(monitor["x"] + left + gap + (i % columns) * (w + gap),
             monitor["y"] + top + gap + (i // columns) * (h + gap), w, h)
            for i in range(count)]


def tile_terminals(context):
    return tile_open_windows(context, category='terminals')


def tile_browsers(context):
    return tile_open_windows(context, category='browsers')


def tile_apps(context):
    return tile_open_windows(context, category='apps')


def tile_open_windows(context, *, category='windows'):
    selectors = {
        'windows': lambda c: True,
        'terminals': is_terminal,
        'browsers': lambda c: c.get('class', '').lower() in BROWSER_CLASSES | {'firefox', 'org.mozilla.firefox', 'brave-browser', 'brave', 'vivaldi-stable', 'microsoft-edge'},
        'apps': lambda c: not is_terminal(c),
    }
    if category not in selectors:
        raise ValueError('Unsupported tiling category')
    selected = selectors[category]
    workspace = (context or {}).get("active", {}).get("workspace", {}).get("id")
    if type(workspace) is not int:
        raise RuntimeError("Could not identify the workspace when recording started")
    if category != 'windows' and workspace <= 0:
        raise RuntimeError("Tile app categories from a regular workspace, not a special workspace")
    hidden_workspace = f'special:keety-tile-{workspace}'

    def belongs(window):
        return (window.get('workspace', {}).get('id') == workspace
                or window.get('workspace', {}).get('name') == hidden_workspace)

    targets = [c for c in context.get("clients", [])
               if belongs(c)
               and c.get("mapped", True)
               and c.get("class") != "io.github.gregorycoppola.Keety"
               and c.get("initialClass") != "io.github.gregorycoppola.Keety"
               and re.fullmatch(r"0x[0-9a-fA-F]+", c.get("address", ""))]
    others = [c for c in targets if not selected(c)
              and c.get('workspace', {}).get('id') == workspace]
    targets = [c for c in targets if selected(c)]
    empty_message = f"No open {category} to tile on this workspace"
    if not targets:
        return empty_message
    clients = json.loads(run(["hyprctl", "clients", "-j"]))
    live = {c["address"]: c for c in clients}
    valid = [t for t in targets if t["address"] in live
             and live[t["address"]].get("mapped", True)
             and belongs(live[t["address"]])
             and all(live[t["address"]].get(k) == t.get(k) for k in ("pid", "class", "stableId"))]
    skipped = len(targets) - len(valid)
    if not valid:
        return f"{empty_message} · Skipped {skipped} closed, moved, or changed windows"
    monitor_id = context["active"].get("monitor", live[valid[0]["address"]].get("monitor"))
    monitor = next((m for m in json.loads(run(["hyprctl", "monitors", "-j"]))
                    if m["id"] == monitor_id and not m.get("disabled")), None)
    if monitor is None:
        raise RuntimeError("The workspace's screen is no longer available")
    # Stable visual order makes repeated commands keep windows in their cells.
    valid.sort(key=lambda t: (*t.get("at", [0, 0])[::-1], t["address"]))
    rectangles = equal_grid(len(valid), monitor)
    tiled = 0
    for target, (x, y, width, height) in zip(valid, rectangles):
        address = target["address"]
        current = next((c for c in json.loads(run(["hyprctl", "clients", "-j"]))
                        if c.get("address") == address), None)
        if (current is None or not current.get("mapped", True)
                or not belongs(current)
                or any(current.get(k) != target.get(k) for k in ("pid", "class", "stableId"))):
            skipped += 1
            continue
        if current.get('workspace', {}).get('name') == hidden_workspace:
            run(['hyprctl', 'dispatch', f'hl.dsp.window.move({{ workspace = "{workspace}", follow = false, window = "address:{address}" }})'])
        run(["hyprctl", "dispatch", 'hl.dsp.window.fullscreen_state({ internal = 0, client = 0, '
             f'action = "set", window = "address:{address}" }})'])
        if len(current.get("grouped", [])) > 1:
            run(["hyprctl", "dispatch", f'hl.dsp.window.move({{ out_of_group = true, window = "address:{address}" }})'])
        run(["hyprctl", "dispatch", f'hl.dsp.window.float({{ action = "on", window = "address:{address}" }})'])
        run(["hyprctl", "dispatch", f'hl.dsp.window.resize({{ x = {width}, y = {height}, relative = false, window = "address:{address}" }})'])
        run(["hyprctl", "dispatch", f'hl.dsp.window.move({{ x = {x}, y = {y}, relative = false, window = "address:{address}" }})'])
        for attempt in range(10):
            updated = next((c for c in json.loads(run(["hyprctl", "clients", "-j"]))
                            if c.get("address") == address), None)
            if (updated is not None and updated.get("workspace", {}).get("id") == workspace
                    and all(updated.get(k) == target.get(k) for k in ("pid", "class", "stableId"))
                    and updated.get("fullscreen") == 0
                    and updated.get("fullscreenClient") == 0
                    and all(abs(a - b) <= 2 for a, b in zip(updated.get("at", []) + updated.get("size", []), (x, y, width, height)))
                    and len(updated.get("at", []) + updated.get("size", [])) == 4):
                break
            time.sleep(.05)
        else:
            raise RuntimeError(f"Tiled {tiled} windows; could not confirm an equal tile for another window (it may have a minimum size)")
        tiled += 1
    message = f"Tiled {tiled} {category}" if tiled else empty_message
    if category != 'windows' and tiled:
        minimized = 0
        for target in others:
            address = target['address']
            current = next((c for c in json.loads(run(['hyprctl', 'clients', '-j']))
                            if c.get('address') == address), None)
            if (current is None or not current.get('mapped', True)
                    or current.get('workspace', {}).get('id') != workspace
                    or any(current.get(k) != target.get(k) for k in ('pid', 'class', 'stableId'))):
                skipped += 1
                continue
            if len(current.get('grouped', [])) > 1:
                run(['hyprctl', 'dispatch', f'hl.dsp.window.move({{ out_of_group = true, window = "address:{address}" }})'])
            run(['hyprctl', 'dispatch', f'hl.dsp.window.move({{ workspace = "{hidden_workspace}", follow = false, window = "address:{address}" }})'])
            updated = next((c for c in json.loads(run(['hyprctl', 'clients', '-j']))
                            if c.get('address') == address), None)
            if (updated is None or updated.get('workspace', {}).get('name') != hidden_workspace
                    or any(updated.get(k) != target.get(k) for k in ('pid', 'class', 'stableId'))):
                raise RuntimeError(f'{message}; could not confirm minimization of another window')
            minimized += 1
        # Hide the holding workspace if a window picker made it visible.
        if minimized:
            for screen in json.loads(run(['hyprctl', 'monitors', '-j'])):
                if screen.get('specialWorkspace', {}).get('name') == hidden_workspace:
                    run(['hyprctl', 'dispatch', f'hl.dsp.workspace.toggle_special("keety-tile-{workspace}")'])
                    break
        message += f' · Minimized {minimized} other windows (tile all windows to restore)'
    if skipped:
        message += f" · Skipped {skipped} closed, moved, or changed windows"
    return message


def maximize_foreground(target):
    target = window_target({'active': target or {}})
    clients = json.loads(run(['hyprctl', 'clients', '-j']))
    current = next((c for c in clients if c.get('address') == target['address']), None)
    if current is None or any(current.get(k) != target.get(k) for k in ('pid', 'class', 'stableId')):
        raise RuntimeError('That window closed or changed. No other window was maximized.')
    address = current['address']
    # Join the floating layer before maximizing: Keety's grid consists of
    # floating windows that can otherwise cover even a focused tiled window.
    run(['hyprctl', 'dispatch', f'hl.dsp.window.fullscreen_state({{ internal = 0, client = 0, action = "set", window = "address:{address}" }})'])
    run(['hyprctl', 'dispatch', f'hl.dsp.window.float({{ action = "on", window = "address:{address}" }})'])
    run(['hyprctl', 'dispatch', f'hl.dsp.window.fullscreen_state({{ internal = 1, client = 1, action = "set", window = "address:{address}" }})'])
    run(['hyprctl', 'dispatch', f'hl.dsp.window.alter_zorder({{ mode = "top", window = "address:{address}" }})'])
    focus(current)
    active = json.loads(run(['hyprctl', 'activewindow', '-j']))
    if (active.get('address') != address or active.get('fullscreen') != 1
            or active.get('fullscreenClient') != 1 or not active.get('floating')
            or active.get('monitor') != current.get('monitor')):
        raise RuntimeError('Could not confirm the window was maximized at the front')


def maximize_current_window(target):
    maximize_foreground(target)
    return 'Maximized this window'


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
    clients = json.loads(run(["hyprctl", "clients", "-j"]))
    moved = next((c for c in clients if c.get("address") == address), None)
    if (moved is None or moved.get("monitor") != destination["id"]
            or moved.get('workspace', {}).get('id') != workspace
            or any(moved.get(k) != target.get(k) for k in ('pid', 'class', 'stableId'))):
        raise RuntimeError("Could not confirm the window moved to the other screen")
    neighbors = [c for c in clients if c.get('monitor') == destination['id']
                 and c.get('workspace', {}).get('id') == workspace and c.get('mapped', True)
                 and c.get('class') != 'io.github.gregorycoppola.Keety'
                 and c.get('initialClass') != 'io.github.gregorycoppola.Keety'
                 and re.fullmatch(r'0x[0-9a-fA-F]+', c.get('address', ''))]
    if len(neighbors) == 1:
        maximize_foreground(moved)
    else:
        tile_open_windows({'active': moved, 'clients': neighbors})
        focus(moved)
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


def focus_named_window(target):
    """Focus the captured terminal identity; a changing title is not identity."""
    if (not is_terminal(target) or not target.get('stableId') or not target.get('pid')
            or not re.fullmatch(r'0x[0-9a-fA-F]+', target.get('address', ''))):
        raise ValueError('Invalid named window target')
    clients = json.loads(run(['hyprctl', 'clients', '-j']))
    current = next((c for c in clients if c.get('address') == target['address']), None)
    if current is None or not is_terminal(current) or any(
            current.get(key) != target.get(key) for key in ('pid', 'class', 'stableId')):
        raise RuntimeError('That terminal closed or was replaced. Try the command again.')
    run(['hyprctl', 'dispatch',
         f'hl.dsp.window.alter_zorder({{ mode = "top", window = "address:{current["address"]}" }})'])
    focus(current)
    return 'Focused ' + (target.get('voice_label') or 'terminal')


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
            present_new_terminal(window)
            return "Opened a new terminal"
        time.sleep(0.1)
    raise RuntimeError("Launch requested, but no new terminal window appeared within 10 seconds")


def present_new_terminal(target):
    maximize_foreground(target)


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
    launcher = launch_desktop(desktop)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        window = app_window(key, json.loads(run(["hyprctl", "clients", "-j"])))
        if window:
            present_browser(window, fullscreen=True)
            return f"Opened {name}"
        if launcher.poll() not in (None, 0):
            raise RuntimeError(f'{name} launcher failed before an app window appeared')
        time.sleep(0.15)
    raise RuntimeError(f"Launch requested, but no {name} window appeared within 15 seconds")


def move_app_other_screen(key, context):
    if key != 'browser' and key not in APPS:
        raise ValueError('Unsupported app to move')
    clients = (context or {}).get('clients', [])
    target = browser_window(clients) if key == 'browser' else app_window(key, clients)
    if target is None:
        raise RuntimeError('No open window found for ' + ('Chrome' if key == 'browser' else APPS[key]['name']))
    return move_other_screen(target)


def maximize_app(key):
    if key != "browser" and key not in APPS:
        raise ValueError("Unsupported app to maximize")
    name = "Chrome" if key == "browser" else APPS[key]["name"]
    clients = json.loads(run(["hyprctl", "clients", "-j"]))
    window = browser_window(clients) if key == "browser" else app_window(key, clients)
    if window is None:
        return f"No open {name} window"
    maximize_foreground(window)
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
