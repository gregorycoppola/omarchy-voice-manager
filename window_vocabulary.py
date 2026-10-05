"""Inject live terminal names into reusable grammar rules; never run actions."""
from dataclasses import dataclass
import hashlib
import json
import re
import subprocess

from command_catalog import TERMINAL_CLASSES, WINDOW_RULES, GRAMMAR, APPS, APP_WORDS, BROWSER
from dataset_source import PROVIDER
from grammar_engine import Word, compile_grammar, normalize
from installed_apps import app_window_names


def spoken(text):
    return normalize(re.sub(r'[^\w\s]', ' ', text, flags=re.UNICODE).replace('_', ' '))


def shell_path(title):
    """Extract the path from a user@host:path shell title without naming the host."""
    match = re.fullmatch(r'([^\s@:\[\]]+)@[^\s:]+:\s*(~(?:/[^|]*)?|/[^|]*)', title.strip())
    if not match:
        return None
    user, path = match.groups()
    if path == '~' or path.startswith('~/'):
        path = user + path[1:]
    elif path.startswith('/home/'):
        path = path[len('/home/'):]
    return path.rstrip('/') or '/'


def window_names(title):
    # Codex titles use "[status] Task | project". Status/spinners change often.
    title = re.sub(r'^\s*\[[^]]*\]\s*', '', title)
    title = re.sub(r'^[^\w]+', '', title)
    pieces = [part.strip() for part in title.split('|') if part.strip()]
    policy = PROVIDER['language_policy']['window_names']
    path = shell_path(title)
    if path is not None:
        name = spoken(path) or 'root'
        forms = [pattern.format(path=name) for pattern in policy.get('shell_forms', ['shell {path}'])]
        basename = spoken(path.rsplit('/', 1)[-1])
        if basename:
            forms.extend(pattern.format(name=basename) for pattern in policy['forms'])
        return forms[0], tuple(dict.fromkeys(forms))
    statuses = set(policy['ignored_statuses'])
    pieces = [piece for piece in pieces if spoken(piece) not in statuses]
    if not pieces:
        return '', ()
    label = ' | '.join(pieces)
    names = [spoken(piece) for piece in pieces] + [spoken(' '.join(pieces))]
    # Plain terminal titles often end in a working-directory path.
    if len(pieces) == 1 and '/' in pieces[0]:
        names.append(spoken(pieces[0].rstrip('/').rsplit('/', 1)[-1]))
    forms = []
    # Spoken task prefixes remain competing names when several windows share
    # them. Require a window noun for these short forms.
    task_tokens = spoken(pieces[0]).split()
    for count in range(1, len(task_tokens)):
        prefix = ' '.join(task_tokens[:count])
        forms.extend(f'{prefix} {noun}' for noun in policy['prefix_nouns'])
    for name in dict.fromkeys(names):
        if not name or len(name) > 180:
            continue
        forms.extend(pattern.format(name=name) for pattern in policy['forms'])
        if len(pieces) >= 2:
            forms.extend(pattern.format(name=name) for pattern in policy['task_forms'])
    return label, tuple(dict.fromkeys(forms))


@dataclass
class WindowVocabulary:
    words: tuple
    expansions: tuple
    targets: dict
    revision: str


def inject_windows(context):
    """The supplied capture owns both the names and the resolved targets."""
    words, targets = [], {}
    app_words = []
    app_names = app_window_names()
    clients = (context or {}).get('clients', [])
    app_counts = {}
    for client in clients:
        if isinstance(client, dict) and client.get('mapped', True):
            app_counts[client.get('class')] = app_counts.get(client.get('class'), 0) + 1
    app_indexes = {}
    for client in clients:
        if not isinstance(client, dict):
            continue
        terminal = client.get('class', '').lower() in TERMINAL_CLASSES
        app = app_names.get(client.get('class')) if not terminal else None
        if (not client.get('class') or client.get('class') == 'io.github.gregorycoppola.Skipper'
                or client.get('initialClass') == 'io.github.gregorycoppola.Skipper'
                or not client.get('mapped', True)
                or not re.fullmatch(r'0x[0-9a-fA-F]+', client.get('address', ''))
                or not client.get('stableId') or not client.get('pid')):
            continue
        if terminal:
            label, forms = window_names(client.get('title') or '')
        else:
            # Built-in app mappings also cover browser webapps whose launcher
            # has no StartupWMClass. Never derive their name from a URL fragment.
            known = [entry['name'] for entry in APPS.values() if client['class'] in entry['classes']]
            label = app.name if app else known[0] if len(known) == 1 else spoken(client['class'].rsplit('.', 1)[-1])
            title = spoken(client.get('title') or '')[:80].strip()
            app_indexes[client['class']] = app_indexes.get(client['class'], 0) + 1
            duplicate = app_counts[client['class']] > 1
            spoken_label = spoken(label)
            numbered = f'{spoken_label} window {app_indexes[client["class"]]}'
            names = list(app.forms if app else (label,))
            if client['class'].lower() in ('chromium', 'google-chrome', 'google-chrome-stable', 'chrome'):
                names.extend(BROWSER.forms)
            for word in APP_WORDS:
                if client['class'] in APPS[word.id]['classes']:
                    names.extend(word.forms)
            names.append(f'{spoken_label} window' if not duplicate else numbered)
            names.append(f'{spoken_label} app window')
            if duplicate and title:
                names.append(f'{title} window')
            forms = tuple(dict.fromkeys(names))
        if not forms:
            continue
        identity = json.dumps([client['stableId'], client['address'], client['pid'], client['class']])
        key = hashlib.sha256(identity.encode()).hexdigest()[:20]
        if key in targets:
            continue
        targets[key] = dict(client, voice_label=label)
        (words if terminal else app_words).append(Word(key, label, forms))
    # Identical project names are deliberately retained as competing meanings.
    expansions = compile_grammar(WINDOW_RULES, {'window': tuple(words)},
        {rule.intent_type: {name: tuple(targets) if value == '$window' else (value,)
                           for name, value in rule.arguments}
         for rule in WINDOW_RULES}, allow_ambiguous=True) if words else ()
    if app_words:
        app_rules = tuple(rule for rule in WINDOW_RULES
                          if rule.intent_type in ('focus_window', 'close_named_window', 'hide_named_window', 'move_named_window'))
        app_expansions = compile_grammar(app_rules, {'window': tuple(app_words)},
            {rule.intent_type: {name: tuple(targets) if value == '$window' else (value,)
                               for name, value in rule.arguments}
             for rule in app_rules}, allow_ambiguous=True)
        # Keep existing generic app commands; explicit window names remain
        # available for selecting a particular app window.
        expansions += tuple(e for e in app_expansions
                            if e.intent.type != 'move_named_window' or e.phrase not in GRAMMAR)
        words.extend(app_words)
    revision = hashlib.sha256(json.dumps([(w.id, w.forms) for w in words]).encode()).hexdigest()[:16]
    return WindowVocabulary(tuple(words), expansions, targets, revision)


def window_action_suggestions(context):
    """List focus, close, hide, and minimize phrases for open windows."""
    vocabulary = inject_windows(context)
    owners = {phrase: {command} for phrase, command in GRAMMAR.items()}
    groups = {}
    for expansion in vocabulary.expansions:
        owners.setdefault(expansion.phrase, set()).add(expansion.command)
        if expansion.intent.type in ('focus_window', 'close_named_window', 'hide_named_window', 'move_named_window'):
            groups.setdefault((dict(expansion.bindings)['window'], expansion.intent.type), []).append(expansion)
    rows = []
    for word in vocabulary.words:
        target = vocabulary.targets[word.id]
        terminal = target['class'].lower() in TERMINAL_CLASSES
        for action, intent_type in (('focus', 'focus_window'), ('close', 'close_named_window'),
                                    ('hide', 'hide_named_window'), ('minimize', 'hide_named_window'), ('move', 'move_named_window')):
            if terminal and action in ('focus', 'close', 'move'):
                continue  # Existing terminal rows have better title-based labels.
            workspace = target.get('workspace', {}).get('id')
            if action in ('hide', 'minimize') and (type(workspace) is not int or workspace <= 0):
                continue
            expansions = groups.get((word.id, intent_type), [])
            forms = list(dict.fromkeys(e.phrase for e in expansions
                                       if e.phrase.startswith(action + ' ') and len(owners[e.phrase]) == 1))
            if not forms:
                continue
            noun = 'terminal' if terminal else 'window'
            preferred = [f'{action} the {form}' for form in word.forms if noun in form]
            if not terminal:
                preferred.insert(0, f'{action} {spoken(word.label)}')
            if action == 'move':
                preferred = [phrase + ' to other screen' for phrase in preferred]
            text = next((phrase for phrase in preferred if phrase in forms), forms[0])
            rows.append(dict(command=expansions[0].command, text=text, forms=forms))
    return rows


def tile_pair_suggestions(context):
    """Offer one valid pair command for each other captured open window."""
    from grammar_engine import Intent
    from window_resolution import WindowResolution, identity
    active = (context or {}).get('active') or {}
    if not active.get('address') or type(active.get('workspace', {}).get('id')) is not int:
        return []
    vocabulary = inject_windows(context)
    if not any(identity(target) == identity(active) for target in vocabulary.targets.values()):
        return []
    resolution = WindowResolution(Intent('tile_pair', (('first', 'this window'),
                                                       ('second', 'the browser'))), context)
    rows = []
    for word in vocabulary.words:
        target = vocabulary.targets[word.id]
        if identity(target) == identity(active):
            continue
        terminal = target['class'].lower() in TERMINAL_CLASSES
        noun = 'terminal' if terminal else 'window'
        preferred = [form for form in word.forms if noun in form]
        forms = []
        for form in dict.fromkeys(preferred + list(word.forms)):
            candidates = resolution.candidates(form)
            if len(candidates) != 1 or identity(candidates[0]) != identity(target):
                continue
            phrase = normalize('tile this window and the ' + form.removeprefix('the '))
            if phrase not in GRAMMAR:
                forms.append(phrase)
        if forms:
            rows.append(dict(command='windows:tile_pair', text=forms[0], forms=forms))
    return rows


def live_windows():
    result = subprocess.run(['hyprctl', 'clients', '-j'], capture_output=True, text=True, timeout=2)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'Could not read open windows')
    return inject_windows({'clients': json.loads(result.stdout)})


def terminal_suggestions(context):
    """Suggest only unambiguous compiled commands for captured live terminals.

    Titles and instantiated phrases remain local; only templates live in the dataset.
    """
    vocabulary = inject_windows(context)
    policy = PROVIDER['language_policy'].get('terminal_suggestions', {})
    owners = {phrase: {command} for phrase, command in GRAMMAR.items()}
    groups = {}
    for expansion in vocabulary.expansions:
        owners.setdefault(expansion.phrase, set()).add(expansion.command)
        key = (expansion.rule_id, dict(expansion.bindings)['window'])
        groups.setdefault(key, []).append(expansion)
    result = []
    rules = policy.get('rules', [{'id': r.id, 'pattern': r.patterns[0]} for r in WINDOW_RULES])
    for rule in rules:
        for word in vocabulary.words:
            if vocabulary.targets[word.id]['class'].lower() not in TERMINAL_CLASSES:
                continue
            expansions = groups.get((rule['id'], word.id), [])
            forms = list(dict.fromkeys(e.phrase for e in expansions if len(owners[e.phrase]) == 1))
            if not forms:
                continue
            # Prefer the project/directory name, then task and complete title.
            pieces = [piece.strip() for piece in word.label.split('|')]
            names = [spoken(pieces[-1].rstrip('/').rsplit('/', 1)[-1])]
            names += [spoken(piece) for piece in pieces] + [spoken(' '.join(pieces))]
            preferred = [normalize(rule['pattern'].replace('<window>',
                policy.get('name_form', '{name} terminal').format(name=name))) for name in names]
            path = shell_path(vocabulary.targets[word.id].get('title', ''))
            if path is not None:
                preferred.insert(0, normalize(rule['pattern'].replace('<window>', word.label)))
            text = next((phrase for phrase in preferred if phrase in forms), forms[0])
            result.append(dict(command=expansions[0].command, text=text, forms=forms))
    return result
