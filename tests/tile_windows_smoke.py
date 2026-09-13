"""Tile only disposable GTK windows on an unused workspace; never target user apps."""
import json
from pathlib import Path
import sys
import threading
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version('Gtk','4.0')
from gi.repository import GLib, Gtk
from os_actions import run, tile_open_windows

APP_ID = 'io.github.gregorycoppola.Keety.TileTest'
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
        assert len(targets) == 2, targets
        keety = [c for c in clients if c['class'] == 'io.github.gregorycoppola.Keety']
        for target in targets:
            address = target['address']
            run(['hyprctl','dispatch',f'hl.dsp.window.move({{workspace = "{workspace}", follow = false, window = "address:{address}"}})'])
            run(['hyprctl','dispatch',f'hl.dsp.window.float({{action = "on", window = "address:{address}"}})'])
        address = targets[0]['address']
        run(['hyprctl','dispatch',f'hl.dsp.window.fullscreen_state({{internal = 2, client = 2, action = "set", window = "address:{address}"}})'])
        targets = [c for c in json.loads(run(['hyprctl','clients','-j'])) if c['class'] == APP_ID]
        context = {'active':targets[0],'clients':targets+keety}
        for _ in range(2):
            assert tile_open_windows(context) == 'Tiled 2 windows'
        time.sleep(.3)
        after = json.loads(run(['hyprctl','clients','-j']))
        tiled = [c for c in after if c['class'] == APP_ID]
        assert len(tiled) == 2
        for c in tiled:
            assert not c['floating'] and c['fullscreen'] == c['fullscreenClient'] == 0, c
            assert c['workspace']['id'] == workspace, c
        a,b = tiled
        assert (a['at'][0]+a['size'][0] <= b['at'][0] or b['at'][0]+b['size'][0] <= a['at'][0]
                or a['at'][1]+a['size'][1] <= b['at'][1] or b['at'][1]+b['size'][1] <= a['at'][1]), tiled
        for before in keety:
            current = next(c for c in after if c['address']==before['address'])
            for key in ['at','size','floating','fullscreen','fullscreenClient','workspace','monitor']:
                assert current[key] == before[key], (key,before,current)
        result.append('PASS: two disposable windows tiled without overlap, repeated command, Keety unchanged')
    except Exception as exc:
        result.append(exc)
    finally:
        GLib.idle_add(app.quit)


def activate(*_):
    for index in range(2):
        window = Gtk.ApplicationWindow(application=app,title=f'Keety tiling test {index}')
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
