"""Real compositor + D-Bus shortcut test; no microphone, model, or user commands."""
import sys
from pathlib import Path
import subprocess
import time
import threading
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gio, GLib, Gtk
from push_to_talk import PushToTalk

from keyboard import build_keyboard
keyboard_bin = build_keyboard()

app = Gtk.Application(application_id='io.github.gregorycoppola.Skipper')
events = []
messages = []
drop_release = False
ptt = PushToTalk(lambda: events.append(('down', time.monotonic())),
                 lambda: events.append(('up', time.monotonic())))
action = Gio.SimpleAction.new('ptt-event', GLib.VariantType.new('s'))
def receive(_, value):
    messages.append(value.get_string())
    if not (drop_release and value.get_string().endswith(":up")):
        ptt.event(value.get_string())
action.connect('activate', receive)
app.add_action(action)
GLib.timeout_add(25, ptt.check_held)
errors = []


def keyboard(args):
    subprocess.run([str(keyboard_bin), *args], check=True, timeout=8)


def exercise():
    global drop_release
    try:
        time.sleep(.3)
        # A tap starts and stops on its own; it must never latch until another tap.
        for _ in range(3):
            events.clear()
            messages.clear()
            keyboard(['d125', 'd19', 's50', 'u19', 'u125'])
            time.sleep(.3)
            assert any(m.endswith(':down') for m in messages), messages
            assert any(m.endswith(':up') for m in messages), messages
            # If delivery is reordered, ignoring the obsolete down is also safe.
            assert [e[0] for e in events] in ([], ['down', 'up']), (events, messages)
            assert ptt.held_session is None, ('tap latched recording', events, messages)
            if events:
                assert events[1][1] - events[0][1] < .3, events
        time.sleep(.5)
        assert ptt.held_session is None
        for super_key, super_first in [(125, False), (125, True), (126, False), (126, True)]:
            events.clear()
            messages.clear()
            release = [f'u{super_key}', 's1100', 'u19'] if super_first else ['u19', 's1100', f'u{super_key}']
            keyboard([f'd{super_key}', 'd19', 's1400', *release])
            time.sleep(.2)
            assert [e[0] for e in events] == ['down', 'up'], (super_first, events, messages)
            assert .8 < events[1][1] - events[0][1] < 1.6, events
            assert any(m.endswith(':up') for m in messages), ('release relied on timeout', messages)
            assert any(m.endswith(':hold') for m in messages), messages
        events.clear()
        drop_release = True
        keyboard(['d125', 'd19', 's1400', 'u19', 'u125', 's1100'])
        assert [e[0] for e in events] == ['down', 'up'], events
        assert 1.4 < events[1][1] - events[0][1] < 2.4, events
        print('PASS: quick taps release without latching; both Super keys and release orders; dropped-release timeout via real Hyprland/D-Bus')
    except Exception as exc:
        errors.append(repr(exc))
    finally:
        GLib.idle_add(app.quit)


def activate(*_):
    window = Gtk.ApplicationWindow(application=app, title='Skipper shortcut test')
    window.set_child(Gtk.Label(label='Testing hold-to-talk; microphone is off'))
    window.present()
    threading.Thread(target=exercise, daemon=True).start()

app.connect('activate', activate)
app.run(['skipper-shortcut-test'])
if errors:
    raise SystemExit(errors[0])
if not messages:
    raise SystemExit('No shortcut events received; close the real Skipper app first')
