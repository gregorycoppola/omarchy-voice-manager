"""Read-only, local most-visited website provider. No browser data is logged."""
from contextlib import closing
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import threading
import time

from websites import website_domain


def history_paths():
    home = Path.home()
    config = Path(os.environ.get('XDG_CONFIG_HOME', home / '.config'))
    paths = []
    for root in (config / 'chromium', config / 'google-chrome',
                 config / 'BraveSoftware/Brave-Browser'):
        paths.extend(sorted(root.glob('*/History')))
    paths.extend(sorted((home / '.mozilla/firefox').glob('*/places.sqlite')))
    return paths


def _read(path, firefox):
    result = {}
    deadline = time.monotonic() + 4
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True,
                                timeout=.15)) as db:
        db.execute('PRAGMA query_only=ON')
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        table, date = ('moz_places', 'last_visit_date') if firefox else ('urls', 'last_visit_time')
        for url, visits, last in db.execute(
                f'SELECT url, visit_count, {date} FROM {table} WHERE visit_count > 0'):
            if time.monotonic() > deadline:
                raise TimeoutError('History read exceeded its time budget')
            if not isinstance(url, str) or not url.lower().startswith(('https://', 'http://')):
                continue
            try:
                host, origin = website_domain(url)
                visits = max(0, int(visits))
                # Firefox uses Unix microseconds; Chromium starts at 1601.
                last = max(0, int(last or 0) / 1_000_000 - (0 if firefox else 11644473600))
            except (TypeError, ValueError):
                continue
            row = result.setdefault(host, dict(id=host, name=host, url=origin,
                                               visit_count=0, last_visit=0))
            row['visit_count'] += visits
            if last >= row['last_visit']:
                row.update(last_visit=last, url=origin)
    return result


def _fingerprint(paths):
    result = []
    for path in paths:
        try:
            info = path.stat()
            result.append((info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns))
        except FileNotFoundError:
            result.append(None)
    return result


def _read_snapshot(path, firefox):
    # Chromium can keep an exclusive lock. Copy the database and any WAL/journal
    # into a private temporary directory, only accepting an unchanged source set.
    # SQLite opens/recoveries affect this disposable copy, never the live browser.
    sources = [path, Path(str(path) + '-wal'), Path(str(path) + '-journal')]
    for _ in range(3):
        with tempfile.TemporaryDirectory(prefix='skipper-history-') as directory:
            target = Path(directory) / path.name
            before = _fingerprint(sources)
            for source, info in zip(sources, before):
                if info is not None:
                    destination = Path(directory) / source.name
                    shutil.copyfile(source, destination)
                    destination.chmod(0o600)
            if before != _fingerprint(sources):
                continue
            # Allow SQLite to recover a copied rollback journal if necessary.
            with closing(sqlite3.connect(target, timeout=.15)) as db:
                db.execute('SELECT count(*) FROM sqlite_master').fetchone()
            return _read(target, firefox)
    raise OSError('Browser history changed while copying')


def most_visited_sites(paths=None, limit=100):
    """Rank hosts by summed recorded visits, then last visit, then hostname."""
    found, unavailable, readable = {}, 0, 0
    paths = history_paths() if paths is None else paths
    for path in paths:
        path = Path(path)
        firefox = path.name == 'places.sqlite'
        try:
            try:
                rows = _read(path, firefox)
            except sqlite3.OperationalError:
                rows = _read_snapshot(path, firefox)
            readable += 1
        except (OSError, sqlite3.Error, TimeoutError):
            unavailable += 1
            continue
        for host, incoming in rows.items():
            if host not in found:
                found[host] = incoming
                continue
            row = found[host]
            row['visit_count'] += incoming['visit_count']
            if incoming['last_visit'] > row['last_visit']:
                row.update(last_visit=incoming['last_visit'], url=incoming['url'])
    sites = sorted(found.values(), key=lambda row: (-row['visit_count'], -row['last_visit'], row['name']))
    message = (f'{unavailable} browser history source(s) unavailable; showing readable history.'
               if unavailable and readable else 'Browser history is currently unavailable. Enter a web address.'
               if unavailable else 'No browser history found. Enter a web address.' if not paths else '')
    return dict(most_visited=sites[:limit], history_message=message,
                history_sources=readable, history_unavailable=unavailable)


class SiteHistory:
    """Short-lived in-memory cache; call refresh from a worker, never the UI thread."""
    def __init__(self):
        self.lock = threading.Lock()
        self.updated = 0
        self.result = None

    def refresh(self, force=False):
        with self.lock:
            if self.result is not None and not force and time.monotonic() - self.updated < 60:
                return self.result
            self.result = most_visited_sites()
            self.updated = time.monotonic()
            return self.result
