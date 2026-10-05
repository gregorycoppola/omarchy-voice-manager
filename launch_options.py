"""Launch, identify a new window, then apply explicit workspace/layout choices."""
import json
from pathlib import Path
import re
import time

import os_actions as desktop
from installed_apps import _entry


def launch_entry(app):
    path = app.path
    entry = _entry(path)
    from gi.repository import Gio
    info = Gio.DesktopAppInfo.new_from_filename(str(path))
    actions = info.list_actions() if info else []
    if 'WebBrowser' in (entry.get('Categories', '') if entry is not None else '') and app.desktop_id.lower() in {'chromium', 'google-chrome', 'google-chrome-stable', 'firefox', 'org.mozilla.firefox', 'brave-browser'}:
        from gi.repository import GLib
        keyfile = GLib.KeyFile()
        keyfile.load_from_file(str(path), GLib.KeyFileFlags.NONE)
        keyfile.set_string('Desktop Entry', 'Exec', entry['Exec'] + ' --new-window')
        Gio.DesktopAppInfo.new_from_keyfile(keyfile).launch([], None)
    elif 'new-window' in actions:
        info.launch_action('new-window', None)
    else:
        return desktop.launch_desktop(path)


def belongs_to_app(window, app):
    if app is None or type(window.get("pid")) is not int:
        return False
    try:
        environment = Path(f"/proc/{window['pid']}/environ").read_bytes().split(b"\0")
        return ("GIO_LAUNCHED_DESKTOP_FILE=" + str(app.path)).encode() in environment
    except OSError:
        return False


def open_with_options(command, options, context, app=None):
    workspace = options['workspace']
    if workspace == 'current':
        workspace = (context or {}).get('active', {}).get('workspace', {}).get('id')
    else:
        workspace = int(workspace)
    if type(workspace) is not int or not 1 <= workspace <= 999999999:
        raise RuntimeError('Open the picker on a regular workspace before launching an app.')
    before = {c['address'] for c in json.loads(desktop.run(['hyprctl', 'clients', '-j']))}
    launcher = None
    if command == 'terminal:new':
        classes = desktop.TERMINAL_CLASSES
        desktop.run(['hyprctl', 'dispatch', 'hl.dsp.exec_cmd("omarchy launch terminal")'])
        name = 'terminal'
    else:
        if app is not None:
            path, name = app.path, app.name
            entry = _entry(path)
            classes = {app.desktop_id.lower()}
            if entry is not None and entry.get('StartupWMClass'):
                classes.add(entry['StartupWMClass'].lower())
        else:
            raise ValueError('Unsupported app launch')
        if path is None or not path.is_file():
            raise RuntimeError(f'{name} is no longer installed')
        launcher = launch_entry(app)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        clients = json.loads(desktop.run(['hyprctl', 'clients', '-j']))
        candidates = [c for c in clients if c.get('address') not in before
                      and c.get('mapped', True)
                      and re.fullmatch(r'0x[0-9a-fA-F]+', c.get('address', ''))
                      and (c.get('class', '').lower() in classes
                           or c.get('initialClass', '').lower() in classes
                           or belongs_to_app(c, app))]
        if len(candidates) > 1:
            raise RuntimeError('Several new app windows appeared; choose one with Move to place it.')
        if candidates:
            window = candidates[0]
            desktop.move_window_workspace(window, workspace)
            # Re-capture after moving, so tiling includes the newly launched window.
            clients = json.loads(desktop.run(['hyprctl', 'clients', '-j']))
            moved = next((c for c in clients if c.get('address') == window['address']
                          and all(c.get(k) == window.get(k) for k in ('pid', 'class', 'stableId'))), None)
            if moved is None or moved.get('workspace', {}).get('id') != workspace:
                raise RuntimeError('The new window changed before its layout could be applied')
            if options.get('tile'):
                desktop.tile_open_windows({'active': moved, 'clients': clients})
            # Keyboard focus alone can leave a tiled app behind floating peers.
            # Recheck its identity and raise it using the current, post-layout stack.
            desktop.focus_named_window(moved)
            return f'Opened {name} on workspace {workspace}' + (' and tiled its windows' if options.get('tile') else '')
        if launcher is not None and launcher.poll() not in (None, 0):
            raise RuntimeError(f'{name} launcher failed')
        time.sleep(.1)
    raise RuntimeError(f'Launch requested, but no identifiable new {name} window appeared. The app may reuse an existing window; no existing window was moved.')
