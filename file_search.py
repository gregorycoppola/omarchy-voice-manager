"""Bounded filename search and explicit default-application opening."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sqlite3
import time
from datetime import datetime
from urllib.parse import urlsplit, unquote
import xml.etree.ElementTree as ET
from contextlib import closing

LIMIT = 80


def recent_database():
    return Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'skipper/recent-files.sqlite3'


def remember_open(path):
    database = recent_database()
    database.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(database, os.O_CREAT | os.O_WRONLY, 0o600)
    os.close(descriptor)
    with closing(sqlite3.connect(database)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS recent_files (path TEXT PRIMARY KEY, opened REAL NOT NULL)')
        db.execute('INSERT INTO recent_files VALUES (?, ?) ON CONFLICT(path) DO UPDATE SET opened=excluded.opened',
                   (str(path), time.time()))
        db.execute('DELETE FROM recent_files WHERE path NOT IN (SELECT path FROM recent_files ORDER BY opened DESC LIMIT 500)')


def recent_files(cancel, home):
    opened = {}
    desktop = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'recently-used.xbel'
    if desktop.exists():
        try:
            if desktop.stat().st_size > 20_000_000:
                raise ValueError('Recent-file history is too large')
            tree = ET.parse(desktop)
            for bookmark in tree.getroot().findall('bookmark'):
                if cancel.is_set():
                    return [], False
                uri = urlsplit(bookmark.get('href', ''))
                if uri.scheme != 'file' or uri.netloc not in ('', 'localhost'):
                    continue
                timestamps = [bookmark.get('visited', '')]
                timestamps += [app.get('modified', '') for app in bookmark.iter()
                               if app.tag.endswith('}application')]
                dates = []
                for value in timestamps:
                    try:
                        dates.append(datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp())
                    except (ValueError, OverflowError):
                        pass
                if dates:
                    path = str(Path(unquote(uri.path)).resolve())
                    opened[path] = max(opened.get(path, 0), max(dates))
        except (OSError, ET.ParseError, ValueError) as exc:
            raise RuntimeError('Desktop recent-file history could not be read. Type a filename to search instead.') from exc
    database = recent_database()
    if database.exists():
        try:
            with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
                for path, stamp in db.execute('SELECT path, opened FROM recent_files'):
                    opened[path] = max(opened.get(path, 0), stamp)
        except sqlite3.Error as exc:
            raise RuntimeError('Skipper recent-file history could not be read. Type a filename to search instead.') from exc
    rows = []
    for name, stamp in sorted(opened.items(), key=lambda item: (-item[1], item[0])):
        if cancel.is_set():
            return [], False
        try:
            path = Path(name).resolve(strict=True)
            if not path.is_file() or not path.is_relative_to(home) or any(p.startswith('.') for p in path.relative_to(home).parts):
                continue
            captured = identity(path)
            key = hashlib.sha256(repr(sorted(captured.items())).encode()).hexdigest()
            folder = '~' if path.parent == home else '~/' + str(path.parent.relative_to(home))
            rows.append(dict(id=key, label=path.name, detail=folder, text='Open file ' + str(path), identity=captured))
            if len(rows) > LIMIT:
                break
        except (OSError, ValueError):
            continue
    return rows[:LIMIT], len(rows) > LIMIT


def identity(path):
    stat = path.stat()
    return dict(path=str(path), device=stat.st_dev, inode=stat.st_ino,
                modified=stat.st_mtime_ns, size=stat.st_size)


def search(query, cancel, home=None):
    home = Path(home or Path.home()).resolve()
    query = query.strip()
    if not query:
        return recent_files(cancel, home)
    pattern = '.*'.join(re.escape(word) for word in query.split())
    command = ['fd', '--type', 'f', '--ignore-case', '--absolute-path', '--print0',
               '--max-results', str(LIMIT + 1), '--exclude', 'node_modules', '--exclude', '.venv',
               '--exclude', '.git', '--', pattern, str(home)]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    elapsed = 0
    try:
        while True:
            if cancel.is_set():
                return [], False
            try:
                output, error = process.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                elapsed += 0.2
                if elapsed >= 5:
                    raise RuntimeError('File search took too long. Try a more specific filename.')
        if process.returncode:
            raise RuntimeError('File search is unavailable. Check that fd is installed and your folders are accessible.')
        paths = [Path(os.fsdecode(path)) for path in output.split(b'\0') if path]
        rows = []
        for path in paths:
            if cancel.is_set():
                return [], False
            try:
                target = path.resolve(strict=True)
                if not target.is_file() or not target.is_relative_to(home):
                    continue
                captured = identity(target)
                key = hashlib.sha256(repr(sorted(captured.items())).encode()).hexdigest()
                folder = '~' if target.parent == home else '~/' + str(target.parent.relative_to(home))
                rows.append(dict(id=key, label=target.name, detail=folder,
                                 text='Open file ' + str(target), identity=captured))
            except (OSError, ValueError):
                continue
        rows.sort(key=lambda row: (row['label'].casefold() != query.casefold(),
                                  not row['label'].casefold().startswith(query.casefold()),
                                  len(row['label']), row['label'].casefold(), row['detail']))
        return rows[:LIMIT], len(paths) > LIMIT
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()


def open_file(captured):
    path = Path(captured['path'])
    try:
        if not path.is_file() or identity(path) != captured:
            raise RuntimeError('That file changed or disappeared. Search for it again.')
    except OSError as exc:
        raise RuntimeError('That file is no longer accessible. Search for it again.') from exc
    subprocess.Popen(['xdg-open', str(path)], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        remember_open(path)
    except (OSError, sqlite3.Error):
        return f'Requested opening {path.name}, but could not save it to recent files.'
    return f'Requested opening {path.name} in its default application.'
