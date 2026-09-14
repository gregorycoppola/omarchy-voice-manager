"""Private append-only command diagnostics outside the source checkout."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import threading

LOG_PATH = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'skipper/commands.jsonl'
_lock = threading.Lock()


def append_event(event, *, path=LOG_PATH, **fields):
    try:
        payload = json.dumps(dict(timestamp=datetime.now(timezone.utc).isoformat(),
                                  event=event, **fields), ensure_ascii=False) + '\n'
        with _lock:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, 'a') as stream:
                stream.write(payload)
    except (OSError, TypeError, ValueError) as exc:
        # Logging failure must not interrupt recording or window actions.
        print(f'Could not write Skipper diagnostics: {exc}', file=sys.stderr)
