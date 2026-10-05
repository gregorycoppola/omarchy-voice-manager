"""Session layout history for mapped Hyprland windows."""
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time


APP_ID = 'io.github.gregorycoppola.Skipper'
ADDRESS = re.compile(r'0x[0-9a-fA-F]+\Z')
WORKSPACE = re.compile(r'(?:[1-9][0-9]*|special:skipper-tile-[1-9][0-9]*)\Z')


def identity(window):
    return tuple(window.get(key) for key in ('address', 'pid', 'class', 'stableId'))


def saved_window(client):
    """Retain only windows and geometry that can be restored safely."""
    if (not isinstance(client, dict) or not client.get('mapped', True)
            or APP_ID in (client.get('class'), client.get('initialClass'))
            or not isinstance(client.get('address'), str) or not ADDRESS.fullmatch(client['address'])
            or not isinstance(client.get('pid'), int) or not client.get('class')
            or not client.get('stableId')):
        return None
    workspace = client.get('workspace', {})
    name = workspace.get('name') or str(workspace.get('id', ''))
    if not isinstance(name, str) or not WORKSPACE.fullmatch(name):
        return None
    at, size = client.get('at'), client.get('size')
    if (not isinstance(at, list) or not isinstance(size, list) or len(at) != 2 or len(size) != 2
            or any(type(value) is not int or abs(value) > 100000 for value in at + size)
            or any(value <= 0 for value in size)):
        return None
    return dict(address=client['address'], pid=client['pid'], **{'class': client['class']},
                stableId=client['stableId'], workspace=name, at=at, size=size,
                floating=bool(client.get('floating', False)),
                fullscreen=int(client.get('fullscreen') or 0),
                fullscreenClient=int(client.get('fullscreenClient') or 0))


def fingerprint(snapshot):
    return json.dumps(sorted(snapshot['windows'], key=lambda window: window['address']),
                      sort_keys=True, separators=(',', ':'))


def valid_saved_window(window):
    return (isinstance(window, dict) and isinstance(window.get('address'), str)
            and ADDRESS.fullmatch(window['address']) is not None
            and type(window.get('pid')) is int and isinstance(window.get('class'), str)
            and bool(window.get('class')) and bool(window.get('stableId'))
            and isinstance(window.get('workspace'), str)
            and WORKSPACE.fullmatch(window['workspace']) is not None
            and isinstance(window.get('at'), list) and isinstance(window.get('size'), list)
            and len(window['at']) == len(window['size']) == 2
            and all(type(value) is int and abs(value) <= 100000
                    for value in window['at'] + window['size'])
            and all(value > 0 for value in window['size'])
            and type(window.get('floating')) is bool
            and type(window.get('fullscreen')) is int and 0 <= window['fullscreen'] <= 3
            and type(window.get('fullscreenClient')) is int and 0 <= window['fullscreenClient'] <= 3)


class LayoutHistory:
    def __init__(self, path, run, *, limit=30, settle_seconds=1.0):
        self.path = Path(path)
        self.run = run
        self.limit = limit
        self.settle_seconds = settle_seconds
        self.lock = threading.RLock()
        self.views = []
        self.index = -1
        self.observed = None
        self.pending = None
        self.changed_at = 0.0
        self._load()

    def _load(self):
        try:
            data = json.loads(self.path.read_text())
            views = data['views']
            index = data['index']
            if (data.get('version') != 1 or not isinstance(views, list)
                    or len(views) > self.limit or type(index) is not int
                    or not -1 <= index < len(views)):
                return
            if any(not isinstance(view, dict) or not isinstance(view.get('windows'), list)
                   or any(not valid_saved_window(window) for window in view['windows']) for view in views):
                return
            self.views, self.index = views, index
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', dir=self.path.parent, delete=False) as handle:
                temporary = Path(handle.name)
                os.fchmod(handle.fileno(), 0o600)
                json.dump({'version': 1, 'index': self.index, 'views': self.views}, handle)
            temporary.replace(self.path)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

    def capture(self):
        clients = json.loads(self.run(['hyprctl', 'clients', '-j']))
        active = json.loads(self.run(['hyprctl', 'activewindow', '-j']))
        windows = [saved for client in clients if (saved := saved_window(client))]
        windows.sort(key=lambda window: window['address'])
        return {'windows': windows, 'focus': active.get('address')}

    def _append(self, snapshot):
        if self.index >= 0 and fingerprint(self.views[self.index]) == fingerprint(snapshot):
            self.views[self.index]['focus'] = snapshot['focus']
            return False
        self.views = self.views[:self.index + 1] + [snapshot]
        if len(self.views) > self.limit:
            self.views = self.views[-self.limit:]
        self.index = len(self.views) - 1
        self._save()
        return True

    def observe(self, *, force=False):
        """Debounce external changes; record completed Skipper actions immediately."""
        with self.lock:
            snapshot = self.capture()
            now = time.monotonic()
            current = fingerprint(snapshot)
            if self.observed is None:
                self.observed = current
                if not self.views:
                    return self._append(snapshot)
                if current != fingerprint(self.views[self.index]):
                    return self._append(snapshot)
                return False
            if current != self.observed:
                self.observed = current
                self.pending, self.changed_at = snapshot, now
            if force:
                self.pending = None
                return self._append(snapshot)
            if self.pending and now - self.changed_at >= self.settle_seconds:
                pending, self.pending = self.pending, None
                return self._append(pending)
            return False

    def save_current(self):
        with self.lock:
            snapshot = self.capture()
            self.observed = fingerprint(snapshot)
            self.pending = None
            return self._append(snapshot)

    def info(self):
        with self.lock:
            return {'can_back': self.index > 0, 'can_forward': self.index < len(self.views) - 1,
                    'position': self.index + 1, 'count': len(self.views)}

    def step(self, direction):
        if direction not in (-1, 1):
            raise ValueError('Choose Back or Forward.')
        with self.lock:
            self.save_current() if self.pending else None
            live = {identity(client): client for client in json.loads(self.run(['hyprctl', 'clients', '-j']))
                    if saved_window(client)}
            target_index = self.index + direction
            while 0 <= target_index < len(self.views):
                view = self.views[target_index]
                survivors = [(saved, live[identity(saved)]) for saved in view['windows']
                             if identity(saved) in live]
                if survivors:
                    break
                target_index += direction
            else:
                return 'No earlier layout with open windows.' if direction < 0 else 'No later layout with open windows.'
            for saved, current in survivors:
                address = saved['address']
                if current.get('workspace', {}).get('name') != saved['workspace']:
                    self.run(['hyprctl', 'dispatch',
                              f'hl.dsp.window.move({{ workspace = "{saved["workspace"]}", follow = false, window = "address:{address}" }})'])
                self.run(['hyprctl', 'dispatch', 'hl.dsp.window.fullscreen_state({ internal = 0, client = 0, '
                          f'action = "set", window = "address:{address}" }})'])
                self.run(['hyprctl', 'dispatch', f'hl.dsp.window.float({{ action = "on", window = "address:{address}" }})'])
                x, y = saved['at']
                width, height = saved['size']
                self.run(['hyprctl', 'dispatch',
                          f'hl.dsp.window.resize({{ x = {width}, y = {height}, relative = false, window = "address:{address}" }})'])
                self.run(['hyprctl', 'dispatch',
                          f'hl.dsp.window.move({{ x = {x}, y = {y}, relative = false, window = "address:{address}" }})'])
                if not saved['floating']:
                    self.run(['hyprctl', 'dispatch', f'hl.dsp.window.float({{ action = "off", window = "address:{address}" }})'])
                if saved['fullscreen'] or saved['fullscreenClient']:
                    self.run(['hyprctl', 'dispatch',
                              f'hl.dsp.window.fullscreen_state({{ internal = {saved["fullscreen"]}, '
                              f'client = {saved["fullscreenClient"]}, action = "set", window = "address:{address}" }})'])
            focus = next((saved for saved, _ in survivors if saved['address'] == view.get('focus')), None)
            if focus and not focus['workspace'].startswith('special:'):
                self.run(['hyprctl', 'dispatch', f'hl.dsp.focus({{ window = "address:{focus["address"]}" }})'])
            for workspace in {saved['workspace'] for saved, _ in survivors
                              if saved['workspace'].startswith('special:skipper-tile-')}:
                monitors = json.loads(self.run(['hyprctl', 'monitors', '-j']))
                if any(monitor.get('specialWorkspace', {}).get('name') == workspace for monitor in monitors):
                    self.run(['hyprctl', 'dispatch',
                              f'hl.dsp.workspace.toggle_special("{workspace.removeprefix("special:")}")'])
            self.index = target_index
            self._save()
            actual = self.capture()
            self.observed = fingerprint(actual)
            self.pending = None
            skipped = len(view['windows']) - len(survivors)
            return (f'Restored layout {self.index + 1} of {len(self.views)} with {len(survivors)} open windows'
                    + (f'; skipped {skipped} closed windows' if skipped else '') + '.')
