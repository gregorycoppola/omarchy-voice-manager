"""Small explicit speech-command vocabulary for the installed Hyprland desktop."""
import json
import math
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from browser_connection import connection
from desktop_commands import DESKTOP_COMMANDS, execute_desktop
from installed_apps import InstalledApp

from command_catalog import APPS, GRAMMAR, SITES, TERMINAL_CLASSES
from intent_matching import normalize
from settings import Settings
from personal_store import DEFAULT_DATA

BROWSER_CLASSES = {"chromium", "google-chrome", "google-chrome-stable", "chrome"}
DEFAULT_BROWSER_DESKTOP = "chromium.desktop"
MAIN_MONITOR = os.environ.get("SKIPPER_MAIN_MONITOR", "")
TERMINAL_CLOSE_INTENTS = {"close:terminal", "close:terminal_current"}


def layout_exclusion():
    """Load private exact app-class exclusions once per layout operation."""
    settings = Settings(DEFAULT_DATA / 'settings.json')
    if settings.error:
        raise RuntimeError(settings.error)
    excluded = set(settings.layout_excluded_classes)
    return lambda window: bool(excluded.intersection(
        (window.get('class'), window.get('initialClass'))))


def require_layout_allowed(window):
    if layout_exclusion()(window):
        raise RuntimeError('This window is excluded from layout changes in your personal settings.')


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


def open_installed_app(app: InstalledApp):
    """Launch only the desktop entry selected by the current app vocabulary."""
    if not app.path.is_file():
        raise RuntimeError(f'{app.name} is no longer installed. Try the command again.')
    launcher = launch_desktop(app.path)
    time.sleep(.1)
    if launcher.poll() not in (None, 0):
        raise RuntimeError(f'{app.name} launcher failed')
    return f'Opening {app.name}'


def focus(window):
    address = window["address"]
    if not re.fullmatch(r"0x[0-9a-fA-F]+", address):
        raise ValueError("Invalid Hyprland window address")
    run(["hyprctl", "dispatch", f'hl.dsp.focus({{ window = "address:{address}" }})'])
    deadline = time.monotonic() + .4
    while True:
        active = json.loads(run(["hyprctl", "activewindow", "-j"]))
        if active.get("address") == address:
            return
        if time.monotonic() >= deadline:
            raise RuntimeError("Hyprland did not focus the selected window")
        time.sleep(.05)


def raise_for_focus(window, clients):
    """Put a tiled target in the floating stack when floats cover its workspace."""
    address = window['address']
    workspace = window.get('workspace', {}).get('id')
    if (not window.get('floating') and isinstance(workspace, int) and workspace > 0
            and any(c.get('address') != address and c.get('floating')
                    and c.get('mapped', True) and c.get('visible', True)
                    and c.get('workspace', {}).get('id') == workspace for c in clients)):
        run(['hyprctl', 'dispatch',
             f'hl.dsp.window.float({{ action = "on", window = "address:{address}" }})'])
    run(['hyprctl', 'dispatch',
         f'hl.dsp.window.alter_zorder({{ mode = "top", window = "address:{address}" }})'])
    focus(window)


def switch_workspace(workspace):
    """Switch the focused monitor to one of the supported numbered workspaces."""
    if type(workspace) is not int or not 1 <= workspace <= 10:
        raise ValueError('Choose workspace 1 through 10.')
    current = json.loads(run(['hyprctl', 'activeworkspace', '-j']))
    if current.get('id') == workspace:
        return f'Already on workspace {workspace}.'
    run(['hyprctl', 'dispatch', f'hl.dsp.focus({{ workspace = "{workspace}" }})'])
    deadline = time.monotonic() + .4
    while True:
        current = json.loads(run(['hyprctl', 'activeworkspace', '-j']))
        if current.get('id') == workspace:
            return f'Switched to workspace {workspace}.'
        if time.monotonic() >= deadline:
            raise RuntimeError(f'Could not confirm workspace {workspace} became active.')
        time.sleep(.05)


def present_browser(window, fullscreen):
    # Retain the legacy argument for existing callers/aliases. All opening
    # paths now share the same maximized, explicitly raised presentation.
    move_to_main_screen(window)
    maximize_foreground(window)


def main_monitor(monitors):
    available = [m for m in monitors if not m.get('disabled')]
    monitor = next((m for m in available if m.get('name') == (MAIN_MONITOR or 'DP-1')), None)
    if monitor is None and not MAIN_MONITOR:
        monitor = next((m for m in available if m.get('focused')), available[0] if available else None)
    if monitor is None:
        raise RuntimeError(f"Screen {MAIN_MONITOR} is not connected" if MAIN_MONITOR else 'No usable screen is connected')
    workspace = monitor.get("activeWorkspace", {}).get("id")
    if not isinstance(workspace, int) or workspace <= 0:
        raise RuntimeError("External screen has no usable active workspace")
    return monitor


def move_to_main_screen(window):
    require_layout_allowed(window or {})
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
    if command in DESKTOP_COMMANDS:
        return execute_desktop(command, run)
    if command == "terminal:new":
        return open_terminal()
    if command in APPS:
        return present_app(command)
    if command.startswith("maximize:"):
        return maximize_app(command.removeprefix("maximize:"))
    if command.startswith("close:"):
        return close_app(command.removeprefix("close:"))
    if command in ("windows", "windows:tile"):
        return tile_open_windows(capture_window_context())
    if command == "windows:list":
        return list_open_windows()
    if command.startswith("site-new:"):
        return present_site(command.removeprefix("site-new:"), new_tab=True)
    if command.startswith("site:"):
        return present_site(command.removeprefix("site:"))
    if command not in ("browser", "browser_fullscreen"):
        raise ValueError("Unsupported voice command")
    fullscreen = command == "browser_fullscreen"
    # Check before launching anything: keep the laptop reserved for Skipper.
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


def list_open_windows():
    """Return every mapped user window, across workspaces, without changing it."""
    clients = json.loads(run(["hyprctl", "clients", "-j"]))
    windows = [c for c in clients if c.get('mapped', True)
               and c.get('class') not in ('io.github.gregorycoppola.Skipper',)
               and c.get('initialClass') not in ('io.github.gregorycoppola.Skipper',)
               and re.fullmatch(r"0x[0-9a-fA-F]+", c.get('address', ''))]
    windows.sort(key=lambda c: (str(c.get('workspace', {}).get('name', c.get('workspace', {}).get('id', ''))),
                                c.get('focusHistoryID', 99999), c.get('title', '')))
    if not windows:
        return 'No open windows.'
    lines = []
    for window in windows:
        workspace = window.get('workspace', {}).get('name', window.get('workspace', {}).get('id', '?'))
        app = window.get('initialClass') or window.get('class') or 'Unknown app'
        title = window.get('title') or app
        lines.append(f'[{workspace}] {app} — {title}')
    return f'{len(lines)} open window{ "s" if len(lines) != 1 else ""}:\n' + '\n'.join(lines)


def open_window_entries(terminals_only=False, browsers_only=False, application=None):
    """Return safe, presentation-ready identities for the window chooser."""
    clients = json.loads(run(['hyprctl', 'clients', '-j']))
    windows = [c for c in clients if c.get('mapped', True)
               and c.get('class') != 'io.github.gregorycoppola.Skipper'
               and c.get('initialClass') != 'io.github.gregorycoppola.Skipper'
               and re.fullmatch(r'0x[0-9a-fA-F]+', c.get('address', ''))]
    if terminals_only:
        windows = [c for c in windows if is_terminal(c)]
    if browsers_only:
        from window_resolution import BROWSERS
        windows = [c for c in windows if c.get('class', '').lower() in BROWSERS]
    if application is not None:
        windows = matching_app_windows(windows, application)
    windows.sort(key=lambda c: (str(c.get('workspace', {}).get('name', c.get('workspace', {}).get('id', ''))),
                                c.get('focusHistoryID', 99999), c.get('title', '')))
    entries = [dict(address=c['address'], pid=c.get('pid'), stableId=c.get('stableId'),
                 **{'class': c.get('class')}, app=c.get('initialClass') or c.get('class') or 'Unknown app',
                 title=c.get('title') or c.get('initialClass') or c.get('class') or 'Unknown app',
                 workspace=str(c.get('workspace', {}).get('name', c.get('workspace', {}).get('id', '?'))))
            for c in windows]
    if terminals_only:
        from window_vocabulary import inject_windows
        vocabulary = inject_windows({'clients': windows})
        owners = {}
        for word in vocabulary.words:
            for form in word.forms:
                owners.setdefault(form, set()).add(word.id)
        by_address = {vocabulary.targets[word.id]['address']: word for word in vocabulary.words}
        for entry in entries:
            word = by_address.get(entry['address'])
            entry['spoken_names'] = sorted((form for form in word.forms if len(owners[form]) == 1),
                                            key=lambda form: (len(form), form)) if word else []
            entry['names_note'] = ('Spoken names: ' + ' · '.join(entry['spoken_names'][:3])
                                   if entry['spoken_names'] else
                                   'No unique spoken name; click to focus.' if word else
                                   'No spoken name available; click to focus.')
    return entries


def focus_listed_window(address, expected=None):
    """Focus a live window selected from the chooser; address is syntax-checked."""
    if not isinstance(address, str) or not re.fullmatch(r'0x[0-9a-fA-F]+', address):
        raise ValueError('Invalid window selection')
    clients = json.loads(run(['hyprctl', 'clients', '-j']))
    window = next((c for c in clients if c.get('address') == address and c.get('mapped', True)), None)
    if window is None:
        raise RuntimeError('That window has already closed')
    if expected and any(window.get(k) != expected.get(k) for k in ('pid', 'class', 'stableId')):
        raise RuntimeError('That window was replaced. List the windows again.')
    raise_for_focus(window, clients)
    return 'Focused ' + (window.get('title') or window.get('class') or 'window')


def prepare_browser_context(context, *, require_focused=False):
    """Launch only when needed; preserve the pre-launch active window and candidates."""
    from copy import deepcopy
    from window_resolution import BROWSERS, identity
    captured = deepcopy(context or {})
    if require_focused:
        target = window_target(captured)
        live = json.loads(run(['hyprctl', 'clients', '-j']))
        if not any(identity(c) == identity(target) and c.get('mapped', True) for c in live):
            raise RuntimeError('The original window closed or changed. Please start a new command.')
    def browsers(clients):
        return [c for c in clients if c.get('class', '').lower() in BROWSERS
                and c.get('mapped', True) and c.get('pid') and c.get('stableId')
                and re.fullmatch(r'0x[0-9a-fA-F]+', c.get('address', ''))]
    if browsers(captured.get('clients', [])):
        return captured
    desktop = next((directory / DEFAULT_BROWSER_DESKTOP
                    for directory in (Path.home() / '.local/share/applications', Path('/usr/share/applications'))
                    if (directory / DEFAULT_BROWSER_DESKTOP).is_file()), None)
    if desktop is None:
        raise RuntimeError('The default browser, Chromium, is not installed')
    launcher = launch_desktop(desktop)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        found = browsers(json.loads(run(['hyprctl', 'clients', '-j'])))
        if found:
            captured['clients'] = captured.get('clients', []) + found
            return captured
        if launcher.poll() not in (None, 0):
            raise RuntimeError('Browser launcher failed before a window appeared')
        time.sleep(.15)
    raise RuntimeError('Launch requested, but no browser window appeared within 10 seconds')


def fullscreen_selected_browser(context, target):
    """Present the selected browser on the captured workspace in true fullscreen."""
    from window_resolution import identity
    address = target.get('address', '')
    workspace = (context or {}).get('active', {}).get('workspace', {}).get('id')
    if not re.fullmatch(r'0x[0-9a-fA-F]+', address) or type(workspace) is not int or workspace <= 0:
        raise RuntimeError('No regular workspace was captured for the browser')
    current = next((c for c in json.loads(run(['hyprctl', 'clients', '-j']))
                    if identity(c) == identity(target) and c.get('mapped', True)), None)
    if current is None:
        raise RuntimeError('The selected browser closed or changed. Please start a new command.')
    if current.get('workspace', {}).get('id') != workspace:
        run(['hyprctl', 'dispatch', f'hl.dsp.window.move({{ workspace = "{workspace}", follow = false, window = "address:{address}" }})'])
    run(['hyprctl', 'dispatch', f'hl.dsp.window.fullscreen_state({{ internal = 2, client = 2, action = "set", window = "address:{address}" }})'])
    focus(current)
    for _ in range(20):
        active = json.loads(run(['hyprctl', 'activewindow', '-j']))
        if (identity(active) == identity(target) and active.get('fullscreen') == 2
                and active.get('fullscreenClient') == 2
                and active.get('workspace', {}).get('id') == workspace):
            return 'Opened the browser in full screen'
        time.sleep(.05)
    raise RuntimeError('Could not confirm fullscreen for the selected browser')


def capture_window_context():
    try:
        active = json.loads(run(["hyprctl", "activewindow", "-j"]))
        if not active.get('workspace'):
            # Hiding the last window leaves no focused client. Retain the
            # workspace so a later tiling command can restore its windows.
            workspace = json.loads(run(['hyprctl', 'activeworkspace', '-j']))
            active = {'workspace': workspace, 'monitor': workspace.get('monitorID')}
        return {"active": active, "clients": json.loads(run(["hyprctl", "clients", "-j"])),
                "monitors": json.loads(run(["hyprctl", "monitors", "-j"]))}
    except Exception:
        return None


def window_target(context):
    target = context.get("active", {}) if context else {}
    if not target.get("mapped", True) or not re.fullmatch(r"0x[0-9a-fA-F]+", target.get("address", "")):
        raise RuntimeError("No focused window was captured when recording started")
    return dict(target)


def equal_grid(count, monitor):
    """Equal-sized grid cells, ordered left to right, respecting monitor scale and panel."""
    if count < 1:
        return []
    width, height = monitor["width"], monitor["height"]
    if monitor.get("transform", 0) % 2:
        width, height = height, width
    scale = monitor.get("scale", 1)
    left, top, right, bottom = monitor.get("reserved", [0, 0, 0, 0])
    width, height = int(width / scale) - left - right, int(height / scale) - top - bottom
    # Prefer two usable columns for 3–6 windows on a typical laptop.
    # Incomplete rows keep the same cell size as the rest of the grid.
    columns = max(1, round(math.sqrt(count)))
    if count == 2:
        columns = 2
    rows = math.ceil(count / columns)
    gap = 12
    h = (height - gap * (rows + 1)) // rows
    rectangles = []
    for row in range(rows):
        row_count = min(columns, count - row * columns)
        w = (width - gap * (columns + 1)) // columns
        if w < 100 or h < 80:
            raise RuntimeError("Too many windows to fit an equal grid on this screen")
        for column in range(row_count):
            rectangles.append((monitor["x"] + left + gap + column * (w + gap),
                               monitor["y"] + top + gap + row * (h + gap), w, h))
    return rectangles


def tile_on_monitor(category, number):
    """Tile the selected display's active workspace, without moving other workspaces."""
    monitors = sorted((m for m in json.loads(run(['hyprctl', 'monitors', '-j']))
                       if not m.get('disabled') and m.get('mirrorOf', 'none') in ('none', None, '')),
                      key=lambda m: m['id'])
    if type(number) is not int or not 1 <= number <= len(monitors):
        raise RuntimeError(f'Monitor {number} is not connected. Available monitors: ' +
                           ', '.join(f"{i}: {m['name']}" for i, m in enumerate(monitors, 1)))
    monitor = monitors[number - 1]
    workspace = monitor.get('activeWorkspace', {})
    if type(workspace.get('id')) is not int or workspace['id'] <= 0:
        raise RuntimeError('That monitor has no active regular workspace.')
    clients = json.loads(run(['hyprctl', 'clients', '-j']))
    context = {'active': {'monitor': monitor['id'], 'workspace': workspace}, 'clients': clients}
    message = tile_open_windows(context, category=category)
    return f"{message} · Monitor {number} ({monitor['name']})"


def tile_terminals(context):
    return tile_open_windows(context, category='terminals')


def tile_browsers(context):
    return tile_open_windows(context, category='browsers')


def tile_apps(context):
    return tile_open_windows(context, category='apps')


def tile_selected_windows(context, targets):
    if len(targets) != 2 or len({t['address'] for t in targets}) != 2:
        raise ValueError('Select two different windows')
    return tile_open_windows(context, selected_targets=targets)


def tile_open_windows(context, *, category='windows', selected_targets=None):
    excluded = layout_exclusion()
    selectors = {
        'windows': lambda c: True,
        'terminals': is_terminal,
        'browsers': lambda c: c.get('class', '').lower() in BROWSER_CLASSES | {'firefox', 'org.mozilla.firefox', 'brave-browser', 'brave', 'vivaldi-stable', 'microsoft-edge'},
        'apps': lambda c: not is_terminal(c),
    }
    if category not in selectors:
        raise ValueError('Unsupported tiling category')
    selected = selectors[category]
    captured_workspace = (context or {}).get("active", {}).get("workspace", {})
    workspace = captured_workspace.get("id")
    # A window picker can reveal a holding workspace. Its name retains the
    # source workspace, even when the regular workspace has no windows left.
    origin = re.fullmatch(r'special:skipper-tile-([1-9][0-9]*)', captured_workspace.get('name', ''))
    if origin:
        workspace = int(origin[1])
    if type(workspace) is not int:
        raise RuntimeError("Could not identify the workspace when recording started")
    if (category != 'windows' or selected_targets is not None) and workspace <= 0:
        raise RuntimeError("Tile app categories from a regular workspace, not a special workspace")
    hidden_workspace = f'special:skipper-tile-{workspace}'

    def belongs(window):
        return (window.get('workspace', {}).get('id') == workspace
                or window.get('workspace', {}).get('name') == hidden_workspace)

    targets = [c for c in context.get("clients", [])
               if belongs(c) and not excluded(c)
               and c.get("mapped", True)
               and c.get("class") != "io.github.gregorycoppola.Skipper"
               and c.get("initialClass") != "io.github.gregorycoppola.Skipper"
               and re.fullmatch(r"0x[0-9a-fA-F]+", c.get("address", ""))]
    others = [c for c in targets if not selected(c)
              and c.get('workspace', {}).get('id') == workspace]
    targets = [c for c in targets if selected(c)]
    empty_message = f"No open {category} to tile on this workspace"
    if selected_targets is not None:
        if any(excluded(c) for c in selected_targets):
            raise RuntimeError("A selected window is excluded from layout changes.")
        targets = list(selected_targets)
        others = []
    if not targets:
        return empty_message
    clients = json.loads(run(["hyprctl", "clients", "-j"]))
    live = {c["address"]: c for c in clients}
    def still_in_place(current, captured):
        if selected_targets is not None:
            return current.get('workspace', {}).get('id') == captured.get('workspace', {}).get('id')
        return belongs(current)

    valid = [t for t in targets if t["address"] in live
             and not excluded(live[t["address"]])
             and live[t["address"]].get("mapped", True)
             and still_in_place(live[t['address']], t)
             and all(live[t["address"]].get(k) == t.get(k) for k in ("pid", "class", "stableId"))]
    skipped = len(targets) - len(valid)
    if selected_targets is not None and skipped:
        raise RuntimeError('A selected window closed, moved, or changed. Please start a new command.')
    if not valid:
        return f"{empty_message} · Skipped {skipped} closed, moved, or changed windows"
    monitor_id = context["active"].get("monitor", live[valid[0]["address"]].get("monitor"))
    monitor = next((m for m in json.loads(run(["hyprctl", "monitors", "-j"]))
                    if m["id"] == monitor_id and not m.get("disabled")), None)
    if monitor is None:
        raise RuntimeError("The workspace's screen is no longer available")
    # Stable visual order makes repeated commands keep windows in their cells.
    if selected_targets is None:
        valid.sort(key=lambda t: (*t.get("at", [0, 0])[::-1], t["address"]))
    rectangles = equal_grid(len(valid), monitor)
    tiled = 0
    for target, (x, y, width, height) in zip(valid, rectangles):
        address = target["address"]
        current = next((c for c in json.loads(run(["hyprctl", "clients", "-j"]))
                        if c.get("address") == address), None)
        if (current is None or not current.get("mapped", True)
                or not still_in_place(current, target)
                or any(current.get(k) != target.get(k) for k in ("pid", "class", "stableId"))):
            if selected_targets is not None:
                raise RuntimeError(f'Tiled {tiled} windows; a selected window closed, moved, or changed.')
            skipped += 1
            continue
        if ((selected_targets is not None and current.get('workspace', {}).get('id') != workspace)
                or current.get('workspace', {}).get('name') == hidden_workspace):
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
    if (category != 'windows' or selected_targets is not None) and tiled:
        if selected_targets is not None:
            # Include windows opened while the picker was up, but preserve the
            # two chosen identities and leave other workspaces alone.
            selected_addresses = {t['address'] for t in selected_targets}
            others = [c for c in json.loads(run(['hyprctl', 'clients', '-j']))
                      if c.get('workspace', {}).get('id') == workspace
                      and c.get('address') not in selected_addresses
                      and c.get('mapped', True)
                      and 'io.github.gregorycoppola.Skipper' not in (c.get('class'), c.get('initialClass'))
                      and re.fullmatch(r'0x[0-9a-fA-F]+', c.get('address', ''))]
        minimized, hide_skipped = hide_window_targets(
            others, workspace, dismiss_hidden=bool(origin) or selected_targets is not None)
        skipped += hide_skipped
        message += f' · Minimized {minimized} other windows (tile all windows to restore)'
    if skipped:
        message += f" · Skipped {skipped} closed, moved, or changed windows"
    return message


def hide_window_targets(targets, workspace, *, dismiss_hidden=False):
    excluded = layout_exclusion()
    targets = [t for t in targets if not excluded(t)]
    hidden_workspace = f'special:skipper-tile-{workspace}'
    skipped = 0
    minimized = 0
    for target in targets:
        address = target['address']
        current = next((c for c in json.loads(run(['hyprctl', 'clients', '-j']))
                        if c.get('address') == address), None)
        if (current is None or excluded(current) or not current.get('mapped', True)
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
            raise RuntimeError(f'Hid {minimized} windows; could not confirm minimization of another window')
        minimized += 1
    # Hide the holding workspace if a window picker made it visible.
    if minimized or dismiss_hidden:
        for screen in json.loads(run(['hyprctl', 'monitors', '-j'])):
            if screen.get('specialWorkspace', {}).get('name') == hidden_workspace:
                run(['hyprctl', 'dispatch', f'hl.dsp.workspace.toggle_special("skipper-tile-{workspace}")'])
                break
    return minimized, skipped


def show_selected_window(target):
    """Restore a Skipper-hidden window to its original workspace and focus it."""
    target = window_target({'active': target})
    address = target['address']
    def current_target():
        clients = json.loads(run(['hyprctl', 'clients', '-j']))
        current = next((c for c in clients
                        if c.get('address') == address), None)
        if (current is None or not current.get('mapped', True)
                or any(current.get(k) != target.get(k) for k in ('pid', 'class', 'stableId'))):
            raise RuntimeError('That window closed or changed. No other window was shown.')
        return current, clients
    current, clients = current_target()
    origin = re.fullmatch(r'special:skipper-tile-([1-9][0-9]*)', current.get('workspace', {}).get('name', ''))
    if origin:
        workspace = int(origin[1])
        run(['hyprctl', 'dispatch', f'hl.dsp.window.move({{ workspace = "{workspace}", follow = false, window = "address:{address}" }})'])
        current, clients = current_target()
        if current.get('workspace', {}).get('id') != workspace:
            raise RuntimeError('Could not confirm the hidden window was restored.')
    raise_for_focus(current, clients)
    return 'Restored and focused the selected window' if origin else 'Focused the selected window'


def matching_app_windows(windows, application):
    """Resolve an app/category argument against exact known names or live classes."""
    from window_resolution import BROWSERS
    from window_vocabulary import spoken
    name = normalize(application)
    if name in ('windows', 'open windows', 'any'):
        return list(windows)
    if name in ('apps', 'applications'):
        return [c for c in windows if not is_terminal(c)]
    if name in ('terminal', 'terminals', 'terminal windows'):
        return [c for c in windows if is_terminal(c)]
    if name in ('browser', 'browsers', 'browser windows'):
        return [c for c in windows if c.get('class', '').lower() in BROWSERS]
    aliases = {'twitter':'x', 'file managers':'files', 'file manager':'files',
               'file browser':'files', 'image viewer':'tensaku', 'image viewers':'tensaku'}
    name = aliases.get(name, name)
    if name in APPS:
        return [c for c in windows if c.get('class') in APPS[name]['classes']]
    classes = ({'chromium','google-chrome','google-chrome-stable','chrome'} if name in ('chrome','chromium')
               else {'firefox','org.mozilla.firefox'} if name == 'firefox' else None)
    if classes is not None:
        return [c for c in windows if c.get('class', '').lower() in classes]
    # App IDs are local data, never shell commands or substring/title guesses.
    name = name.removesuffix(' windows').strip()
    return [c for c in windows if any(name in (normalize(value), spoken(value), spoken(value.rsplit('.', 1)[-1]))
                                     for value in (c.get('class') or '', c.get('initialClass') or '') if value)]


def show_all_windows(context, application):
    """Raise each matching captured window, restoring Skipper-hidden windows first."""
    from grammar_engine import Intent
    from window_resolution import WindowResolution

    resolution = WindowResolution(Intent('show_all_application'), context)
    targets = matching_app_windows(resolution.windows, application)
    if not targets:
        return f'No open {application} windows to show'
    # End with the most recently used match on top, using the captured ordering.
    targets = sorted(targets, key=lambda c: c.get('focusHistoryID', 99999), reverse=True)
    shown = 0
    failures = []
    for target in targets:
        try:
            show_selected_window(target)
            shown += 1
        except RuntimeError as exc:
            failures.append(str(exc))
    message = f'Brought {shown} open {application} windows to the front'
    if failures:
        message += f' · Could not show {len(failures)} windows: {failures[0]}'
    return message


def hide_current_window(context):
    target = window_target(context)
    workspace = target.get('workspace', {}).get('id')
    if type(workspace) is not int or workspace <= 0:
        raise RuntimeError('The captured window was not on a regular workspace')
    if 'io.github.gregorycoppola.Skipper' in (target.get('class'), target.get('initialClass')):
        raise RuntimeError('Skipper is excluded from window hiding')
    hidden, skipped = hide_window_targets([target], workspace)
    if skipped:
        return 'That window closed, moved, or changed. No window was hidden.'
    return 'Hid this window (tile all windows to restore)'


def hide_windows(context, category):
    if category not in {'terminals', 'apps'}:
        raise ValueError('Unsupported hiding category')
    workspace = (context or {}).get('active', {}).get('workspace', {}).get('id')
    if type(workspace) is not int or workspace <= 0:
        raise RuntimeError('Could not identify a regular workspace when recording started')
    targets = [c for c in context.get('clients', [])
               if c.get('workspace', {}).get('id') == workspace
               and c.get('mapped', True)
               and c.get('class') != 'io.github.gregorycoppola.Skipper'
               and c.get('initialClass') != 'io.github.gregorycoppola.Skipper'
               and re.fullmatch(r'0x[0-9a-fA-F]+', c.get('address', ''))
               and bool(is_terminal(c)) == (category == 'terminals')]
    if not targets:
        return f'No visible {category} to hide on this workspace'
    hidden, skipped = hide_window_targets(targets, workspace)
    message = f'Hid {hidden} {category} (tile all windows to restore)'
    if skipped:
        message += f' · Skipped {skipped} closed, moved, or changed windows'
    return message


def maximize_foreground(target):
    require_layout_allowed(target or {})
    target = window_target({'active': target or {}})
    clients = json.loads(run(['hyprctl', 'clients', '-j']))
    current = next((c for c in clients if c.get('address') == target['address']), None)
    if current is None or any(current.get(k) != target.get(k) for k in ('pid', 'class', 'stableId')):
        raise RuntimeError('That window closed or changed. No other window was maximized.')
    address = current['address']
    # Join the floating layer before maximizing: Skipper's grid consists of
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


def move_window_workspace(target, workspace):
    if type(workspace) is not int or not 1 <= workspace <= 999999999:
        raise ValueError('Use a positive workspace number.')
    target = window_target({'active': target})
    require_layout_allowed(target)
    if not target.get('pid') or not target.get('stableId'):
        raise RuntimeError('Could not identify the captured window safely.')
    address = target['address']
    def current_window():
        current = next((c for c in json.loads(run(['hyprctl', 'clients', '-j']))
                        if c.get('address') == address), None)
        if (current is None or not current.get('mapped', True)
                or any(current.get(k) != target.get(k) for k in ('pid', 'class', 'stableId'))):
            raise RuntimeError('That window closed or changed. No other window was moved.')
        return current
    current = current_window()
    if current.get('workspace', {}).get('id') == workspace:
        return f'This window is already on workspace {workspace}.'
    if len(current.get('grouped', [])) > 1:
        run(['hyprctl', 'dispatch', f'hl.dsp.window.move({{ out_of_group = true, window = "address:{address}" }})'])
    run(['hyprctl', 'dispatch', f'hl.dsp.window.move({{ workspace = "{workspace}", follow = false, window = "address:{address}" }})'])
    if current_window().get('workspace', {}).get('id') != workspace:
        raise RuntimeError('Could not confirm the window moved to the requested workspace.')
    return f'Moved this window to workspace {workspace}.'


def move_other_screen(target):
    require_layout_allowed(target or {})
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
                 and c.get('class') != 'io.github.gregorycoppola.Skipper'
                 and c.get('initialClass') != 'io.github.gregorycoppola.Skipper'
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



def all_terminal_targets(context):
    """Freeze the complete terminal set from the command-start snapshot."""
    if context is None or 'clients' not in context:
        raise RuntimeError('Could not identify terminals when the command started. Try again.')
    return list({c['address']: dict(c) for c in context['clients'] if is_terminal(c)}.values())


def close_terminals(targets):
    """Close only captured identities; preflight the whole batch before dispatch."""
    if not targets:
        return 'No open terminal windows.'
    if any(not is_terminal(target) for target in targets):
        raise ValueError('Invalid terminal target')
    clients = json.loads(run(['hyprctl', 'clients', '-j']))
    remaining = []
    for target in targets:
        current = next((c for c in clients if c.get('address') == target['address']), None)
        if current is None:
            continue
        if not is_terminal(current) or any(current.get(k) != target.get(k) for k in ('pid', 'class', 'stableId')):
            raise RuntimeError('A terminal changed. No windows were closed; try again.')
        remaining.append(target)
    requested = 0
    for target in remaining:
        try:
            message = close_terminal(target)
            if 'already closed' not in message:
                requested += 1
        except Exception as exc:
            raise RuntimeError(f'Stopped after requesting {requested} terminal closes: {exc}') from exc
    return f'Asked {requested} terminal windows to close. Respond to any confirmations they show.'


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
    """Focus the captured window identity; a changing title is not identity."""
    if (not target.get('class') or not target.get('stableId') or not target.get('pid')
            or not re.fullmatch(r'0x[0-9a-fA-F]+', target.get('address', ''))):
        raise ValueError('Invalid named window target')
    clients = json.loads(run(['hyprctl', 'clients', '-j']))
    current = next((c for c in clients if c.get('address') == target['address']), None)
    if current is None or not current.get('mapped', True) or any(
            current.get(key) != target.get(key) for key in ('pid', 'class', 'stableId')):
        raise RuntimeError('That window closed or was replaced. Try the command again.')
    if re.fullmatch(r'special:skipper-tile-[1-9][0-9]*', current.get('workspace', {}).get('name', '')):
        show_selected_window(target)
        return 'Focused ' + (target.get('voice_label') or 'window')
    raise_for_focus(current, clients)
    return 'Focused ' + (target.get('voice_label') or 'window')


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


def close_selected_window(target):
    """Close the captured choice only; never substitute a new most-recent window."""
    address = target.get('address', '')
    if not re.fullmatch(r'0x[0-9a-fA-F]+', address):
        raise ValueError('Invalid window address')
    clients = json.loads(run(['hyprctl', 'clients', '-j']))
    current = next((c for c in clients if c.get('address') == address), None)
    if (not current or not current.get('mapped', True)
            or not target.get('pid') or not target.get('stableId')
            or any(current.get(k) != target.get(k) for k in ('pid', 'class', 'stableId'))):
        raise RuntimeError('The selected window closed or changed. Please start a new command.')
    run(['hyprctl', 'dispatch', f'hl.dsp.window.close({{ window = "address:{address}" }})'])
    for _ in range(20):
        clients = json.loads(run(['hyprctl', 'clients', '-j']))
        if not any(c.get('address') == address and c.get('mapped', True) for c in clients):
            return 'Closed the selected window'
        time.sleep(.1)
    return 'Asked the selected window to close. Check it for a confirmation.'


def open_url_in_browser_window(url, target):
    """Open a new tab in one frozen native Chrome/Chromium window."""
    from window_resolution import identity
    from url_entry import normalize_url
    url = normalize_url(url)
    if (not isinstance(target, dict)
            or target.get('class', '').lower() not in {'chromium', 'google-chrome', 'google-chrome-stable', 'chrome'}
            or not re.fullmatch(r'0x[0-9a-fA-F]+', target.get('address', ''))
            or not target.get('pid') or not target.get('stableId')):
        raise RuntimeError('Choose a connected Chrome/Chromium window first')

    def verify():
        active = json.loads(run(['hyprctl', 'activewindow', '-j']))
        if identity(active) != identity(target) or not active.get('mapped', True):
            raise RuntimeError('Selected browser changed or lost focus; website was not opened')

    def bring_forward():
        clients = json.loads(run(['hyprctl', 'clients', '-j']))
        current = next((c for c in clients if identity(c) == identity(target) and c.get('mapped', True)), None)
        if current is None:
            raise RuntimeError('Selected browser closed or changed; website was not opened')
        focus(current)
        verify()

    return connection.open_url_in_window(url, bring_forward, verify)


def close_browser_tabs(target):
    """Clear tabs only after native identity and extension focus agree."""
    from window_resolution import identity
    if target.get('class', '').lower() not in {'chromium', 'google-chrome', 'google-chrome-stable', 'chrome'}:
        raise RuntimeError('Closing tabs requires the connected Chrome/Chromium browser')
    if (not re.fullmatch(r'0x[0-9a-fA-F]+', target.get('address', ''))
            or not target.get('pid') or not target.get('stableId')):
        raise RuntimeError('Browser window identity unavailable')

    def verify():
        active = json.loads(run(['hyprctl', 'activewindow', '-j']))
        if identity(active) != identity(target) or not active.get('mapped', True):
            raise RuntimeError('The selected browser changed or lost focus. No tabs were closed.')

    def bring_forward():
        clients = json.loads(run(['hyprctl', 'clients', '-j']))
        current = next((c for c in clients if identity(c) == identity(target) and c.get('mapped', True)), None)
        if current is None:
            raise RuntimeError('The selected browser closed or changed. No tabs were closed.')
        focus(current)
        verify()

    result = connection.reset_tabs(bring_forward, verify)
    return f"Closed {result['closed']} tabs; one blank tab remains."


def present_site(key, *, new_tab=False):
    if key not in SITES:
        raise ValueError("Unsupported website command")
    site = SITES[key]
    # A site request is tab navigation, not a layout request. Preserve an
    # existing browser's workspace, size, fullscreen state, and tiling. When
    # Chromium is closed, its normal launcher/compositor policy decides how
    # the new browser window is placed.
    window = browser_window(json.loads(run(["hyprctl", "clients", "-j"])))
    if window is None:
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
                break
            if launcher.poll() not in (None, 0):
                raise RuntimeError('Chrome launcher failed before a browser window appeared')
            time.sleep(0.15)
        else:
            raise RuntimeError("Launch requested, but no browser window appeared within 10 seconds")
    selected = connection.open_another(site) if new_tab else connection.bring_up(site)
    action = 'Opened another' if new_tab else ('Reused' if selected['reused'] else 'Opened')
    return f"{action} {site['name']} tab"
