"""Voice controls as a Wayland layer surface, outside desktop window tiling."""
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gtk4LayerShell', '1.0')
from gi.repository import Gdk, Gtk, Gtk4LayerShell


def configure(window):
    if not Gtk4LayerShell.is_supported():
        raise RuntimeError('Voice dropdown requires a Wayland compositor with layer-shell support.')
    Gtk4LayerShell.init_for_window(window)
    Gtk4LayerShell.set_namespace(window, 'skipper-voice-debug')
    Gtk4LayerShell.set_layer(window, Gtk4LayerShell.Layer.OVERLAY)
    Gtk4LayerShell.set_anchor(window, Gtk4LayerShell.Edge.TOP, True)
    Gtk4LayerShell.set_anchor(window, Gtk4LayerShell.Edge.RIGHT, True)
    Gtk4LayerShell.set_margin(window, Gtk4LayerShell.Edge.TOP, 40)
    Gtk4LayerShell.set_margin(window, Gtk4LayerShell.Edge.RIGHT, 12)
    Gtk4LayerShell.set_exclusive_zone(window, 0)
    Gtk4LayerShell.set_keyboard_mode(window, Gtk4LayerShell.KeyboardMode.ON_DEMAND)
    window.set_title('Skipper voice debug')
    window.set_decorated(False)
    window.connect('close-request', lambda *_: hide(window))
    keys = Gtk.EventControllerKey()
    keys.connect('key-pressed', lambda controller, key, *rest: hide(window) if key == Gdk.KEY_Escape else False)
    window.add_controller(keys)


def hide(window):
    window.set_visible(False)
    return True
