"""Personal website bookmarks and recent picker destinations, stored in private SQLite."""
from pathlib import Path
from contextlib import closing
import os
import sqlite3
from urllib.parse import urlsplit
from uuid import uuid4

import personal_store
from url_entry import normalize_url


def website_domain(url):
    parsed = urlsplit(normalize_url(url))
    host = parsed.hostname
    authority = f'[{host}]' if ':' in host else host
    if parsed.port:
        authority += f':{parsed.port}'
    return host, f'{parsed.scheme}://{authority}/'


def browser_domains(paths=None):
    """Explicit import only: read local browser SQLite databases and retain origins."""
    if paths is None:
        home = Path.home()
        config = Path(os.environ.get('XDG_CONFIG_HOME', home/'.config'))
        paths = []
        for root in (config/'chromium', config/'google-chrome', config/'BraveSoftware/Brave-Browser'):
            paths.extend(root.glob('*/History'))
        paths.extend((home/'.mozilla/firefox').glob('*/places.sqlite'))
    found = {}
    for path in paths:
        try:
            with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True, timeout=.2)) as db:
                db.execute('PRAGMA query_only=ON')
                query = ('SELECT url FROM moz_places ORDER BY last_visit_date DESC LIMIT 2000'
                         if Path(path).name == 'places.sqlite' else
                         'SELECT url FROM urls ORDER BY last_visit_time DESC LIMIT 2000')
                for (url,) in db.execute(query):
                    try:
                        name, origin = website_domain(url)
                    except (ValueError, TypeError):
                        continue
                    found.setdefault(name, dict(id=origin, name=name, url=origin))
        except sqlite3.Error:
            continue
    return list(found.values())[:100]


class Websites:
    def __init__(self, data):
        self.path = Path(data) / 'websites.json'
        try:
            self.data = personal_store.load(self.path)
        except FileNotFoundError:
            self.data = {'version': 1, 'sites': [dict(id='twitter', name='Twitter / X', url='https://x.com/')], 'recent': []}
        if (not isinstance(self.data, dict) or self.data.get('version') != 1
                or not isinstance(self.data.get('sites'), list) or not isinstance(self.data.get('recent'), list)):
            raise ValueError('Could not read your saved websites.')
        self.data.setdefault('browser_history', [])
        if not isinstance(self.data['browser_history'], list):
            raise ValueError('Could not read your imported website domains.')
        for row in self.data['sites'] + self.data['recent'] + self.data['browser_history']:
            if (not isinstance(row, dict) or not isinstance(row.get('name'), str)
                    or not isinstance(row.get('id'), str) or not isinstance(row.get('url'), str)):
                raise ValueError('Could not read your saved websites.')
            normalize_url(row['url'])

    def view(self):
        saved = {row['url'] for row in self.data['sites']}
        recent = [row for row in self.data['recent'] if row['url'] not in saved]
        shown = saved | {row['url'] for row in recent}
        return dict(sites=self.data['sites'], recent=recent,
                    browser_history=[row for row in self.data['browser_history'] if row['url'] not in shown])

    def import_history(self):
        self.data['browser_history'] = browser_domains()
        personal_store.save(self.path, self.data)
        return len(self.data['browser_history'])

    def save(self, name, url, key=None):
        url = normalize_url(url)
        if not isinstance(name, str) or len(name.strip()) > 80:
            raise ValueError('Use a website name up to 80 characters.')
        name = name.strip() or urlsplit(url).hostname
        existing = next((row for row in self.data['sites'] if row['id'] == key), None) if key else None
        if key and existing is None:
            raise ValueError('That saved website no longer exists.')
        if existing is None:
            existing = next((row for row in self.data['sites'] if row['url'] == url), None)
        if existing:
            existing.update(name=name, url=url)
        else:
            self.data['sites'].append(dict(id=uuid4().hex, name=name, url=url))
        personal_store.save(self.path, self.data)

    def remove(self, key):
        self.data['sites'] = [row for row in self.data['sites'] if row['id'] != key]
        personal_store.save(self.path, self.data)

    def resolve(self, text):
        if not isinstance(text, str) or not text.strip():
            raise ValueError('Choose a saved website or enter a web address.')
        matches = [row for row in self.data['sites'] + self.data['recent'] + self.data['browser_history'] if row['name'].casefold() == text.strip().casefold()]
        urls = {row['url'] for row in matches}
        if len(urls) > 1:
            raise ValueError('More than one website has that name. Choose it from the list.')
        return next(iter(urls)) if urls else normalize_url(text)

    def remember(self, url):
        name, url = website_domain(url)
        self.data['recent'] = [dict(id=url, name=name, url=url)] + [row for row in self.data['recent'] if website_domain(row['url'])[0] != name]
        self.data['recent'] = self.data['recent'][:20]
        personal_store.save(self.path, self.data)
