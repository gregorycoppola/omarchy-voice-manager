"""Close a disposable GTK window through the real compositor; no user app targets."""
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import GLib, Gtk
from command_catalog import APPS
from os_actions import close_app

app_id = 'io.github.gregorycoppola.Keety.CloseTest'
APPS['_close_test'] = {'name': 'Keety test', 'classes': {app_id}}
app = Gtk.Application(application_id=app_id)
result = []
worker = None


def close_test():
    try:
        result.append(close_app('_close_test'))
    except Exception as exc:
        result.append(exc)
    finally:
        GLib.idle_add(app.quit)


def activate(*_):
    window = Gtk.ApplicationWindow(application=app, title='Keety close-command test')
    window.set_default_size(300, 100)
    window.set_child(Gtk.Label(label='Testing close on this temporary window'))
    window.present()

    def start():
        global worker
        worker = threading.Thread(target=close_test)
        worker.start()
        return False
    GLib.timeout_add(500, start)


app.connect('activate', activate)
app.run(['keety-close-test'])
if worker:
    worker.join(timeout=15)
assert result == ['Closed Keety test window'], result
print('PASS: real compositor closed only the disposable test app window')
