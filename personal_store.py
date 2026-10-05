"""Private per-user SQLite documents, with transactional legacy JSON migration.

The path accepted by callers identifies the old file and its namespace only.
No new personal JSON files are written. Existing originals remain as backups.
"""
import json
import os
from pathlib import Path
import sqlite3
from command_store import CommandStore

DEFAULT_DATA = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'skipper'
DEFAULT_STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'skipper'
SECTIONS = {'websites.json': ('sites', list), 'aliases.json': ('aliases', dict), 'corrections.json': ('rules', dict),
            'actions.json': ('actions', dict), 'settings.json': ('confirm_terminal_close', bool)}


def database_path(legacy):
    legacy = Path(legacy)
    directory = DEFAULT_STATE if legacy.parent.resolve() == DEFAULT_DATA.resolve() else legacy.parent
    return directory / 'command-history.sqlite3'


def store_for(legacy):
    return CommandStore(database_path(legacy))


def load(legacy):
    legacy = Path(legacy)
    try:
        if not database_path(legacy).exists() and not legacy.exists():
            raise FileNotFoundError(legacy)
        store = store_for(legacy)
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS personal (name TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            row = db.execute('SELECT payload FROM personal WHERE name=?', (legacy.name,)).fetchone()
            if row:
                return json.loads(row[0])
            if not legacy.exists():
                raise FileNotFoundError(legacy)
            payload = json.loads(legacy.read_text())
            field, kind = SECTIONS[legacy.name]
            if not isinstance(payload, dict) or type(payload.get(field)) is not kind:
                raise ValueError('Invalid legacy personal data')
            if legacy.name != 'settings.json' and payload.get('version') != 1:
                raise ValueError('Unsupported legacy personal data version')
            if legacy.name == 'corrections.json' and not isinstance(payload.get('events'), list):
                raise ValueError('Invalid correction audit history')
            legacy.chmod(0o600)
            db.execute('INSERT INTO personal(name,payload) VALUES (?,?)', (legacy.name, json.dumps(payload)))
            return payload
    except sqlite3.Error as exc:
        raise OSError('Could not access private SQLite preferences') from exc


def save(legacy, payload):
    try:
        store = store_for(legacy)
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS personal (name TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('INSERT INTO personal(name,payload) VALUES (?,?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload',
                       (Path(legacy).name, json.dumps(payload, ensure_ascii=False)))
    except sqlite3.Error as exc:
        raise OSError('Could not save private SQLite preferences') from exc


def initialize(data=DEFAULT_DATA):
    """Create empty tables and import each existing namespace on first launch."""
    store = store_for(Path(data) / 'aliases.json')
    for name in SECTIONS:
        try:
            load(Path(data) / name)
        except FileNotFoundError:
            pass
    return store
