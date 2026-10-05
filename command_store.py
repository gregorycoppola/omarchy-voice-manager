"""Private SQLite command attempts; never save desktop targets or recordings here."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
from datetime import datetime, timezone


class CommandStore:
    def __init__(self, path):
        self.path = Path(path)
        # Refuse accidental history inside any checkout, including public snapshots.
        if any((parent / '.git').exists() for parent in self.path.resolve().parents):
            raise ValueError('Command history must be outside a Git checkout')
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.parent.chmod(0o700)
        fd = os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(fd)
        self.path.chmod(0o600)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS commands (
                    id INTEGER PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    text TEXT NOT NULL,
                    normalized TEXT NOT NULL,
                    source TEXT NOT NULL,
                    command TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'recognized'
                );
                CREATE INDEX IF NOT EXISTS commands_normalized ON commands(normalized, id DESC);
                CREATE TABLE IF NOT EXISTS migrations (name TEXT PRIMARY KEY);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def insert(db, text, command, source, timestamp=None, status='recognized'):
        if not isinstance(text, str) or not text.strip() or len(text) > 2000 or not isinstance(command, str) or not command:
            return
        text = text.strip()
        db.execute('INSERT INTO commands(timestamp,text,normalized,source,command,status) VALUES (?,?,?,?,?,?)',
                   (timestamp or datetime.now(timezone.utc).isoformat(), text,
                    ' '.join(text.casefold().split()), source, command, status))

    def record(self, text, command, source):
        # Each recognized invocation gets its own row, including repeat uses.
        with self.connect() as db:
            self.insert(db, text, command, source)

    def import_log(self, path):
        """One-time full streaming import. Old recognition is not proof of execution."""
        path = Path(path)
        if not path.exists():
            return
        with self.connect() as db:
            if db.execute('SELECT 1 FROM migrations WHERE name=?', ('diagnostics-v1',)).fetchone():
                return
            with path.open(errors='replace') as stream:
                for line in stream:
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(event, dict) and event.get('event') == 'parsed':
                        self.insert(db, event.get('written'), event.get('command'),
                                    event.get('input_source') or 'legacy', event.get('timestamp'), 'imported')
            db.execute('INSERT INTO migrations(name) VALUES (?)', ('diagnostics-v1',))

    def recent_entries(self):
        """Distinct wording plus its last recognized command, newest first."""
        with self.connect() as db:
            return [dict(text=row[0], command=row[1]) for row in db.execute('''
                SELECT text, command FROM commands WHERE id IN
                (SELECT MAX(id) FROM commands GROUP BY normalized) ORDER BY id DESC
            ''')]

    def recent(self):
        return [row['text'] for row in self.recent_entries()]

    def written_counts(self):
        """Count recognized typed uses by resolved command, not by wording."""
        with self.connect() as db:
            return {command: count for command, count in db.execute('''
                SELECT command, COUNT(*) FROM commands
                WHERE source = 'written' GROUP BY command
            ''')}
