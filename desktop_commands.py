"""Authored local desktop actions; never interprets shell text."""
import json

from dataset_source import PROVIDER

# Local handler IDs bound the capabilities; labels and wording come from the dataset.
EXECUTOR_IDS = {'volume:up', 'volume:down', 'volume:mute', 'volume:unmute',
                'brightness:up', 'brightness:down', 'media:play', 'media:pause',
                'media:next', 'media:previous'}
if set(PROVIDER['desktop_commands']) != EXECUTOR_IDS:
    raise ValueError('Dataset desktop commands do not match installed executor capabilities')
DESKTOP_COMMANDS = {key: (value[0], tuple(value[1]))
                    for key, value in PROVIDER['desktop_commands'].items()}


def execute_desktop(command, run, context=None):
    if command not in DESKTOP_COMMANDS:
        raise ValueError('Unknown desktop command')
    kind, action = command.split(':')
    if kind == 'volume':
        if action in ('up', 'down'):
            run(['omarchy', 'audio', 'output', 'volume', 'raise' if action == 'up' else 'lower'])
            return 'Volume increased' if action == 'up' else 'Volume decreased'
        sink = run(['omarchy', 'audio', 'output', 'sink']).strip()
        if not sink or sink.startswith('-') or any(c.isspace() for c in sink):
            raise RuntimeError('Could not identify the audio output')
        run(['pactl', 'set-sink-mute', sink, '1' if action == 'mute' else '0'])
        muted = run(['env', 'LC_ALL=C', 'pactl', 'get-sink-mute', sink]).strip().lower()
        if muted != ('mute: yes' if action == 'mute' else 'mute: no'):
            raise RuntimeError('Could not confirm the requested mute state')
        return 'Sound muted' if action == 'mute' else 'Sound unmuted'
    if kind == 'brightness':
        monitors = json.loads(run(['hyprctl', 'monitors', '-j']))
        captured = (context or {}).get('active', {}).get('monitor')
        monitor = next((m for m in monitors if not m.get('disabled') and
                        (m.get('id') == captured if captured is not None else m.get('focused'))), None)
        if not monitor or not monitor.get('name'):
            raise RuntimeError('The captured display is no longer available')
        run(['omarchy', 'brightness', 'display', '--monitor', monitor['name'],
             '+5%' if action == 'up' else '5%-'])
        return 'Brightness increased' if action == 'up' else 'Brightness decreased'
    result = run(['omarchy-shell', 'media', action]).strip()
    if result != 'ok':
        raise RuntimeError('No media player handled that command')
    return {'play': 'Playback requested', 'pause': 'Pause requested',
            'next': 'Next track requested', 'previous': 'Previous track requested'}[action]
