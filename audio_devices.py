"""Live audio defaults through the PipeWire PulseAudio compatibility interface."""
import hashlib
import json
import subprocess

KINDS = {'output': ('sinks', 'sink', 'audio output'), 'input': ('sources', 'source', 'microphone')}


def call(*args):
    try:
        result = subprocess.run(['pactl', *args], capture_output=True, text=True, timeout=4)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('Audio controls are unavailable. Check that the audio service is running.') from exc
    if result.returncode:
        raise RuntimeError('The audio service could not complete the request.')
    return result.stdout.strip()


def snapshot(direction):
    collection, kind, label = KINDS[direction]
    default = call('get-default-' + kind)
    objects = json.loads(call('--format=json', 'list', collection))
    rows = []
    for obj in objects:
        name = obj.get('name')
        props = obj.get('properties') or {}
        serial = str(props.get('object.serial') or '')
        if not name or not serial:
            continue  # Never trust a reusable numeric index on its own.
        # Playback monitors are not microphones, except a configured default
        # (some processed microphones are deliberately exposed as monitors).
        mapped_microphone = bool(props.get('omarchy.asahi-mic.owner')) or name in ('omarchy_asahi_mic', 'omarchy_asahi_mic.monitor')
        if direction == 'output' and mapped_microphone:
            continue
        if direction == 'input' and name.endswith('.monitor') and name != default and not mapped_microphone:
            continue
        port = next((p for p in obj.get('ports', []) if p.get('name') == obj.get('active_port')), {})
        if port.get('availability') == 'not available' and name != default:
            continue
        identity = dict(direction=direction, name=name, serial=serial)
        key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        title = obj.get('description') or props.get('node.description') or name
        if mapped_microphone:
            title = 'Built-in microphone (Omarchy stereo adapter)'
        rows.append(dict(id=key, label=title, detail=name, current=name == default,
                         identity=identity, text=f'Switch {label} to {title}'))
    rows.sort(key=lambda row: (not row['current'], row['label'].casefold(), row['detail']))
    return rows


def set_default(identity):
    direction = identity['direction']
    current = next((row for row in snapshot(direction) if row['identity'] == identity), None)
    if current is None:
        raise RuntimeError('That device disconnected or changed. Choose it again.')
    label = KINDS[direction][2]
    if current['current']:
        return f"{current['label']} is already the default {label}."
    call('set-default-' + KINDS[direction][1], identity['name'])
    verified = next((row for row in snapshot(direction) if row['identity'] == identity), None)
    if not verified or not verified['current']:
        raise RuntimeError('The audio service did not confirm the new default. Refresh the device list.')
    return f"Default {label}: {current['label']}. Existing apps may retain their own routing."
