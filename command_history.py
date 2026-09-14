"""Recent original recognition events, supplemented by older saved recordings."""
import json
from pathlib import Path


def recent_recordings(directory, log_path, limit=100):
    records = {}
    for path in sorted(Path(directory).glob('*.wav'), reverse=True)[:limit]:
        transcript = path.with_suffix('.txt')
        records[str(path)] = dict(recording=str(path), heard=transcript.read_text() if transcript.exists() else '',
                                  parsed=None, outcome='', timestamp=path.stem.replace('_', ' '))
    try:
        with Path(log_path).open('rb') as stream:
            stream.seek(0, 2)
            offset = max(0, stream.tell() - 4 * 1024 * 1024)
            stream.seek(offset)
            if offset:
                stream.readline()
            lines = stream.read().decode('utf-8', errors='replace').splitlines()
    except FileNotFoundError:
        lines = []
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue  # An interrupted final append must not hide other history.
        if not isinstance(event, dict):
            continue
        path = event.get('recording')
        if not path or Path(path).parent != Path(directory):
            continue
        record = records.setdefault(path, dict(recording=path, heard='', parsed=None, outcome='',
                                              timestamp=Path(path).stem.replace('_', ' ')))
        if event.get('event') == 'transcript':
            record['_retry'] = not event.get('commands_enabled', False)
        # A later "transcribe again" must not rewrite what the voice command originally heard.
        if event.get('event') == 'transcript' and event.get('commands_enabled') and 'original' not in record:
            record['heard'] = event.get('text', '')
            record['original'] = True
        if event.get('event') == 'parsed' and event.get('result') and record['parsed'] is None:
            record['parsed'] = event['result']
            record['command'] = event.get('command')
        if event.get('event') == 'state' and not record.get('_retry') and event.get('state') in ('Ready', 'Error', 'Confirm'):
            record['outcome'] = event.get('message', '')
    return sorted(records.values(), key=lambda record: record['recording'], reverse=True)[:limit]
