"""Explicit desired-state controls; listing never changes system state."""
import os
import re
import shutil
import subprocess
import time


def run(*args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=8,
                            env=dict(os.environ, LC_ALL='C'))
    if result.returncode:
        raise RuntimeError('The system could not complete that request.')
    return result.stdout.strip()


def bluez():
    from gi.repository import Gio
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    objects = bus.call_sync('org.bluez', '/', 'org.freedesktop.DBus.ObjectManager',
                           'GetManagedObjects', None, None, Gio.DBusCallFlags.NONE, 4000, None).unpack()[0]
    return bus, objects


def night_state():
    if not shutil.which('hyprsunset'):
        raise RuntimeError('Night light is not installed.')
    if subprocess.run(['pgrep', '-x', 'hyprsunset'], capture_output=True).returncode:
        return False
    match = re.search(r'\b([0-9]{4,5})\b', run('hyprctl', 'hyprsunset', 'temperature'))
    if not match:
        raise RuntimeError('Night-light state is unavailable.')
    return int(match[1]) < 6000


def snapshot():
    rows = []
    def control(key, label, getter):
        try:
            enabled = getter()
            detail, available = ('On' if enabled else 'Off'), True
        except Exception:
            enabled, detail, available = None, 'Unavailable', False
        for desired in (True, False):
            verb = 'enable' if desired else 'disable'
            rows.append(dict(id=verb + ':' + key, verb=verb, label=label,
                text=verb + ' ' + label, detail=detail, available=available,
                selection=dict(kind=key, enabled=desired)))
    control('night-light', 'night light', night_state)
    control('wifi', 'Wi-Fi', lambda: run('nmcli', 'radio', 'wifi') == 'enabled')
    try:
        _, objects = bluez()
        adapters = [(path, interfaces['org.bluez.Adapter1']) for path, interfaces in objects.items()
                    if 'org.bluez.Adapter1' in interfaces]
        for path, adapter in adapters:
            label = 'Bluetooth' if len(adapters) == 1 else 'Bluetooth — ' + adapter.get('Alias', path.rsplit('/', 1)[-1])
            for desired in (True, False):
                verb = 'enable' if desired else 'disable'
                rows.append(dict(id=verb + ':' + path, verb=verb, label=label, text=verb + ' ' + label,
                    detail='On' if adapter.get('Powered') else 'Off', available=True,
                    selection=dict(kind='bluetooth', path=path, address=adapter['Address'], enabled=desired)))
        for path, interfaces in objects.items():
            device = interfaces.get('org.bluez.Device1')
            if not device or not device.get('Paired'):
                continue
            label = device.get('Alias') or device.get('Name') or device['Address']
            for desired in (True, False):
                verb = 'connect' if desired else 'disconnect'
                rows.append(dict(id=verb + ':' + path, verb=verb, label=label, text=verb + ' ' + label,
                    detail='Bluetooth · ' + ('Connected' if device.get('Connected') else 'Disconnected'), available=True,
                    selection=dict(kind='device', path=path, address=device['Address'], enabled=desired)))
        if not adapters:
            raise RuntimeError('No Bluetooth adapters')
    except Exception:
        for verb in ('enable', 'disable'):
            rows.append(dict(id=verb + ':bluetooth-unavailable', verb=verb, label='Bluetooth',
                text=verb + ' Bluetooth', detail='Unavailable', available=False, selection={}))
    return rows


def execute(selection):
    kind, desired = selection['kind'], selection['enabled']
    if kind == 'wifi':
        if (run('nmcli', 'radio', 'wifi') == 'enabled') != desired:
            run('nmcli', 'radio', 'wifi', 'on' if desired else 'off')
        if (run('nmcli', 'radio', 'wifi') == 'enabled') != desired:
            raise RuntimeError('Wi-Fi did not reach the requested state.')
        return 'Wi-Fi radio ' + ('enabled.' if desired else 'disabled.')
    if kind == 'night-light':
        if night_state() != desired:
            if subprocess.run(['pgrep', '-x', 'hyprsunset'], capture_output=True).returncode:
                run('systemctl', '--user', 'start', 'hyprsunset.service')
            for attempt in range(10):
                try:
                    run('hyprctl', 'hyprsunset', 'temperature', '4000' if desired else '6500')
                    time.sleep(0.2)
                    if night_state() == desired:
                        break
                except RuntimeError:
                    time.sleep(0.2)
            else:
                raise RuntimeError('Night light did not reach the requested state.')
            subprocess.run(['omarchy-shell', '-q', 'nightlight', 'refresh'], capture_output=True, timeout=4)
        return 'Night light ' + ('enabled.' if desired else 'disabled.')
    from gi.repository import Gio, GLib
    bus, objects = bluez()
    interface = 'org.bluez.Adapter1' if kind == 'bluetooth' else 'org.bluez.Device1'
    properties = objects.get(selection['path'], {}).get(interface, {})
    if properties.get('Address') != selection['address']:
        raise RuntimeError('That Bluetooth target disappeared or changed. Choose it again.')
    key = 'Powered' if kind == 'bluetooth' else 'Connected'
    if bool(properties.get(key)) != desired:
        if kind == 'bluetooth':
            bus.call_sync('org.bluez', selection['path'], 'org.freedesktop.DBus.Properties', 'Set',
                GLib.Variant('(ssv)', (interface, 'Powered', GLib.Variant('b', desired))),
                None, Gio.DBusCallFlags.NONE, 8000, None)
        else:
            bus.call_sync('org.bluez', selection['path'], interface, 'Connect' if desired else 'Disconnect',
                          None, None, Gio.DBusCallFlags.NONE, 15000, None)
    for attempt in range(10):
        _, objects = bluez()
        current = objects.get(selection['path'], {}).get(interface, {})
        if current.get('Address') == selection['address'] and current.get(key) == desired:
            return ('Bluetooth ' + ('enabled.' if desired else 'disabled.')) if kind == 'bluetooth' else ('Device ' + ('connected.' if desired else 'disconnected.'))
        time.sleep(0.2)
    raise RuntimeError('Bluetooth did not confirm the requested state.')
