"""Read-only, exact-only vocabulary for visible installed desktop applications."""
from dataclasses import dataclass
import configparser
import hashlib
import os
from pathlib import Path
import re
import shutil
import shlex
import subprocess

from grammar_engine import Word, compile_grammar, normalize
from command_catalog import INSTALLED_APP_RULES, GRAMMAR


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


def app_suggestions(apps):
    """Group discoverable launch phrases into one selector row per command."""
    rows = {}
    for expansion in apps.expansions:
        row = rows.setdefault(expansion.command, dict(
            command=expansion.command, text=expansion.phrase, forms=[], optionalOpen=True))
        if expansion.phrase not in row['forms']:
            row['forms'].append(expansion.phrase)
    for app in apps.apps:
        row = rows.get('desktop-app:' + app.desktop_id)
        if row is not None:
            row['text'] = 'open ' + app.name
    result = list(rows.values())
    terminal_id = configured_terminal_id()
    terminal = apps.targets.get(terminal_id)
    if terminal is not None:
        result.insert(0, dict(command='terminal:new', text='open terminal',
                             forms=['open terminal', 'open a terminal', 'open new terminal',
                                    'open a new terminal'], optionalOpen=True,
                             description='Default terminal: ' + terminal.name))
    return result


def configured_terminal_id():
    """Ask the default-terminal resolver without launching a terminal."""
    if not shutil.which('xdg-terminal-exec'):
        return None
    try:
        result = subprocess.run(['xdg-terminal-exec', '--print-id'], capture_output=True,
                                text=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode:
        return None
    return result.stdout.strip().split(':', 1)[0].removesuffix('.desktop')


def app_window_names():
    """Use explicit launcher window classes, never browser title guesses."""
    names = {}
    for app in discover_installed_apps(reserved_forms=reserved_app_forms(GRAMMAR)).apps:
        entry = _entry(app.path)
        window_class = entry.get('StartupWMClass', '').strip() if entry is not None else ''
        if window_class:
            names.setdefault(window_class, []).append(app)
    return {key: apps[0] for key, apps in names.items() if len(apps) == 1}


def discover_installed_apps(*, roots=None, reserved_forms=(), for_picker=False):
    """Return launchable desktop entries with unambiguous spoken names only."""
    candidates = []
    for desktop_id, path in _desktop_paths(application_dirs() if roots is None else roots).items():
        entry = _entry(path)
        if entry is None or entry.get('Type') != 'Application':
            continue
        if entry.get('Hidden', '').lower() == 'true' or entry.get('NoDisplay', '').lower() == 'true':
            continue
        categories = set(entry.get('Categories', '').split(';'))
        if (not for_picker and (entry.get('Terminal', '').lower() == 'true'
                or entry.get('DBusActivatable', '').lower() == 'true'
                or 'TerminalEmulator' in categories)):
            continue
        executable = entry.get('TryExec', '').strip()
        if executable and not shutil.which(executable):
            continue
        if for_picker:
            try:
                executable = shlex.split(entry.get('Exec', ''))[0]
            except (ValueError, IndexError):
                continue
            if not shutil.which(executable):
                continue
        forms = (tuple(dict.fromkeys(filter(None, (normalize(entry.get('Name', '')),
                                                   _spoken(entry.get('Name', ''))))))
                 if for_picker else _forms(entry, desktop_id))
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
