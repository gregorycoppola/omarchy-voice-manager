"""Tile only disposable GTK windows on an unused workspace; never target user apps."""
import json
from pathlib import Path
import sys
import threading
import time
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version('Gtk','4.0')
from gi.repository import GLib, Gtk
from os_actions import run, tile_open_windows, tile_terminals, tile_apps, hide_windows, fullscreen_selected_browser, tile_selected_windows

APP_ID = 'io.github.gregorycoppola.Skipper.TileTest'
app = Gtk.Application(application_id=APP_ID)
windows = []
result = []
worker = None


def test():
    try:
        occupied = {w['id'] for w in json.loads(run(['hyprctl','workspaces','-j']))}
        workspace = next(i for i in range(9000,9100) if i not in occupied)
        clients = json.loads(run(['hyprctl','clients','-j']))
        targets = [c for c in clients if c['class'] == APP_ID]
        assert len(targets) == 4, targets
        skipper = [c for c in clients if c['class'] == 'io.github.gregorycoppola.Skipper']
        for target in targets:
            address = target['address']
            run(['hyprctl','dispatch',f'hl.dsp.window.move({{workspace = "{workspace}", follow = false, window = "address:{address}"}})'])
            run(['hyprctl','dispatch',f'hl.dsp.window.float({{action = "on", window = "address:{address}"}})'])
        address = targets[0]['address']
        run(['hyprctl','dispatch',f'hl.dsp.window.fullscreen_state({{internal = 2, client = 2, action = "set", window = "address:{address}"}})'])
        targets = [c for c in json.loads(run(['hyprctl','clients','-j'])) if c['class'] == APP_ID]
        context = {'active':targets[0],'clients':targets+skipper}
        for _ in range(2):
            assert tile_open_windows(context) == 'Tiled 4 windows'
        time.sleep(.3)
        after = json.loads(run(['hyprctl','clients','-j']))
        tiled = [c for c in after if c['class'] == APP_ID]
        assert len(tiled) == 4
        for c in tiled:
            assert c['floating'] and c['fullscreen'] == c['fullscreenClient'] == 0, c
            assert c['workspace']['id'] == workspace, c
        assert len({tuple(c['size']) for c in tiled}) == 1, tiled
        assert len({c['at'][0] for c in tiled}) == 2, tiled
        assert len({c['at'][1] for c in tiled}) == 2, tiled
        for i,a in enumerate(tiled):
            for b in tiled[i+1:]:
                assert (a['at'][0]+a['size'][0] <= b['at'][0] or b['at'][0]+b['size'][0] <= a['at'][0]
                        or a['at'][1]+a['size'][1] <= b['at'][1] or b['at'][1]+b['size'][1] <= a['at'][1]), tiled
        # Classify two disposable windows as terminals to exercise real
        # compositor hide/restore dispatches without touching real terminals.
        terminal_addresses = {c['address'] for c in tiled[:2]}
        with patch('os_actions.is_terminal', side_effect=lambda c: c['address'] in terminal_addresses):
            for action, count in [(tile_terminals, 2), (tile_apps, 2), (tile_open_windows, 4)]:
                targets = [c for c in json.loads(run(['hyprctl', 'clients', '-j'])) if c['class'] == APP_ID]
                active = next(c for c in targets if c['workspace']['id'] == workspace)
                print(f'Checking {action.__name__}', flush=True)
                action({'active': active, 'clients': targets + skipper})
                time.sleep(.3)
                targets = [c for c in json.loads(run(['hyprctl', 'clients', '-j'])) if c['class'] == APP_ID]
                visible = [c for c in targets if c['workspace']['id'] == workspace]
                assert len(visible) == count, targets
                assert all(abs(c['size'][axis] - visible[0]['size'][axis]) <= 2
                           for c in visible for axis in (0, 1)), visible
                if action == tile_terminals:
                    assert {c['address'] for c in visible} == terminal_addresses
                elif action == tile_apps:
                    assert not terminal_addresses.intersection(c['address'] for c in visible)
                for c in targets:
                    assert c['workspace']['id'] == workspace or c['workspace']['name'] == f'special:skipper-tile-{workspace}'
        with patch('os_actions.is_terminal', side_effect=lambda c: c['address'] in terminal_addresses):
            anchor = dict(visible[0])
            for category in ('terminals', 'apps'):
                targets = [c for c in json.loads(run(['hyprctl', 'clients', '-j'])) if c['class'] == APP_ID]
                hide_windows({'active': anchor, 'clients': targets + skipper}, category)
            targets = [c for c in json.loads(run(['hyprctl', 'clients', '-j'])) if c['class'] == APP_ID]
            assert all(c['workspace']['name'] == f'special:skipper-tile-{workspace}' for c in targets)
            # Simulate the captured context after a picker focuses a hidden
            # window. Both category tiling and restore-all must find the origin.
            tile_terminals({'active': targets[0], 'clients': targets + skipper})
            targets = [c for c in json.loads(run(['hyprctl', 'clients', '-j'])) if c['class'] == APP_ID]
            assert {c['address'] for c in targets if c['workspace']['id'] == workspace} == terminal_addresses
            hidden_target = next(c for c in targets if c['workspace']['id'] != workspace)
            tile_open_windows({'active': hidden_target, 'clients': targets + skipper})
            targets = [c for c in json.loads(run(['hyprctl', 'clients', '-j'])) if c['class'] == APP_ID]
            assert all(c['workspace']['id'] == workspace for c in targets)
        after = json.loads(run(['hyprctl', 'clients', '-j']))
        for before in skipper:
            current = next(c for c in after if c['address']==before['address'])
            for key in ['at','size','floating','fullscreen','fullscreenClient','workspace','monitor']:
                assert current[key] == before[key], (key,before,current)
        # Exercise the failing five-window case with a browser-like minimum width.
        created = threading.Event()
        def add_wide_window():
            window = Gtk.ApplicationWindow(application=app, title='Wide grid test')
            window.set_size_request(500, 100)
            window.present()
            windows.append(window)
            created.set()
            return False
        GLib.idle_add(add_wide_window)
        assert created.wait(3), 'Fifth test window did not open'
        for _ in range(30):
            current = [c for c in json.loads(run(['hyprctl', 'clients', '-j'])) if c['class'] == APP_ID]
            if len(current) == 5:
                break
            time.sleep(.1)
        assert len(current) == 5
        extra = next(c for c in current if c['address'] not in {t['address'] for t in targets})
        run(['hyprctl', 'dispatch', f'hl.dsp.window.move({{workspace = "{workspace}", follow = false, window = "address:{extra["address"]}"}})'])
        targets = [c for c in json.loads(run(['hyprctl', 'clients', '-j'])) if c['class'] == APP_ID]
        assert tile_open_windows({'active': targets[0], 'clients': targets}) == 'Tiled 5 windows'
        tiled = [c for c in json.loads(run(['hyprctl', 'clients', '-j'])) if c['class'] == APP_ID]
        rows = sorted({c['at'][1] for c in tiled})
        assert [sum(c['at'][1] == y for c in tiled) for y in rows] == [2, 2, 1], tiled
        assert all(c['size'][0] >= 500 for c in tiled), tiled
        assert len({tuple(c['size']) for c in tiled}) == 1, tiled
        context = {'active': tiled[0], 'clients': tiled}
        assert fullscreen_selected_browser(context, tiled[1]) == 'Opened the browser in full screen'
        pair = [c for c in json.loads(run(['hyprctl', 'clients', '-j']))
                if c['address'] in (tiled[0]['address'], tiled[1]['address'])]
        by_address = {c['address']: c for c in pair}
        selected = [by_address[tiled[0]['address']], by_address[tiled[1]['address']]]
        assert 'Tiled 2 windows' in tile_selected_windows(context, selected)
        visible = [c for c in json.loads(run(['hyprctl', 'clients', '-j']))
                   if c['class'] == APP_ID and c['workspace']['id'] == workspace]
        assert len(visible) == 2, visible
        by_address = {c['address']: c for c in visible}
        assert by_address[selected[0]['address']]['at'][0] < by_address[selected[1]['address']]['at'][0]
        result.append('PASS: grids, hide/restore, true fullscreen, and return to an isolated side-by-side pair')
    except Exception as exc:
        result.append(exc)
    finally:
        GLib.idle_add(app.quit)


def activate(*_):
    for index in range(4):
        window = Gtk.ApplicationWindow(application=app,title=f'Skipper tiling test {index}')
        window.set_default_size(200,100)
        window.present()
        windows.append(window)
    def start():
        global worker
        worker = threading.Thread(target=test)
        worker.start()
        return False
    GLib.timeout_add(500,start)

app.connect('activate',activate)
app.run(['tile-test'])
if worker:
    worker.join(timeout=20)
assert len(result)==1 and isinstance(result[0],str), result
print(result[0])
