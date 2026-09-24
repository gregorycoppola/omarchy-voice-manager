"""Read-only, exact-only vocabulary for visible installed desktop applications."""
from dataclasses import dataclass
import configparser
import hashlib
import os
from pathlib import Path
import re
import shutil

from grammar_engine import Word, compile_grammar, normalize
from command_catalog import INSTALLED_APP_RULES


@dataclass(frozen=True)
class InstalledApp:
    desktop_id: str
    name: str
    path: Path
    forms: tuple[str, ...]


@dataclass(frozen=True)
class InstalledApps:
    apps: tuple[InstalledApp, ...]
    expansions: tuple
    targets: dict
    revision: str


def application_dirs():
    data = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    shared = os.environ.get('XDG_DATA_DIRS', '/usr/local/share:/usr/share').split(':')
    return tuple(dict.fromkeys((data / 'applications', *(Path(path) / 'applications' for path in shared if path))))


def _desktop_paths(roots):
    """First XDG match owns an ID, including an intentional Hidden override."""
    paths = {}
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob('*.desktop')):
            desktop_id = str(path.relative_to(root)).replace('/', '-')[:-8]
            paths.setdefault(desktop_id, path)
    return paths


def _entry(path):
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read_string(path.read_text(errors='replace'))
        return parser['Desktop Entry'] if parser.has_section('Desktop Entry') else None
    except (OSError, configparser.Error):
        return None


def _spoken(value):
    return normalize(re.sub(r'[^\w\s]', ' ', value, flags=re.UNICODE).replace('_', ' '))


def _forms(entry, desktop_id):
    names = [_spoken(entry.get('Name', '')), _spoken(entry.get('GenericName', ''))]
    return tuple(dict.fromkeys(name for name in names if 2 <= len(name) <= 80 and len(name.split()) <= 8))


def reserved_app_forms(grammar):
    """Forms whose open/launch phrase is already owned by Skipper's grammar."""
    return {phrase.removeprefix(prefix) for phrase in grammar
            for prefix in ('open ', 'launch ') if phrase.startswith(prefix)}


def discover_installed_apps(*, roots=None, reserved_forms=()):
    """Return launchable desktop entries with unambiguous spoken names only."""
    candidates = []
    for desktop_id, path in _desktop_paths(application_dirs() if roots is None else roots).items():
        entry = _entry(path)
        if entry is None or entry.get('Type') != 'Application':
            continue
        if entry.get('Hidden', '').lower() == 'true' or entry.get('NoDisplay', '').lower() == 'true':
            continue
        categories = set(entry.get('Categories', '').split(';'))
        if (entry.get('Terminal', '').lower() == 'true' or entry.get('DBusActivatable', '').lower() == 'true'
                or 'TerminalEmulator' in categories):
            continue
        executable = entry.get('TryExec', '').strip()
        if executable and not shutil.which(executable):
            continue
        forms = _forms(entry, desktop_id)
        if forms:
            candidates.append(InstalledApp(desktop_id, entry.get('Name', '').strip(), path, forms))
    reserved = set(reserved_forms)
    counts = {}
    for app in candidates:
        for form in app.forms:
            counts[form] = counts.get(form, 0) + 1
    apps = []
    for app in candidates:
        forms = tuple(form for form in app.forms if counts[form] == 1 and form not in reserved)
        if forms:
            apps.append(InstalledApp(app.desktop_id, app.name, app.path, forms))
    words = tuple(Word(app.desktop_id, app.name, app.forms) for app in apps)
    targets = {app.desktop_id: app for app in apps}
    rules = INSTALLED_APP_RULES
    expansions = compile_grammar(rules, {'installed_app': words},
        {'open_installed_app': {'desktop': tuple(targets)}}) if words else ()
    revision = hashlib.sha256(repr([(app.desktop_id, app.name, app.forms, str(app.path))
                                    for app in apps]).encode()).hexdigest()[:16]
    return InstalledApps(tuple(apps), expansions, targets, revision)
