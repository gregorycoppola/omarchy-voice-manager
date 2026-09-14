"""Inject live terminal names into reusable grammar rules; never run actions."""
from dataclasses import dataclass
import hashlib
import json
import re
import subprocess

from command_catalog import TERMINAL_CLASSES, WINDOW_RULES
from grammar_engine import Word, compile_grammar, normalize


def spoken(text):
    return normalize(re.sub(r'[^\w\s]', ' ', text, flags=re.UNICODE).replace('_', ' '))


def window_names(title):
    # Codex titles use "[status] Task | project". Status/spinners change often.
    title = re.sub(r'^\s*\[[^]]*\]\s*', '', title)
    title = re.sub(r'^[^\w]+', '', title)
    pieces = [part.strip() for part in title.split('|') if part.strip()]
    statuses = {'action required', 'working', 'thinking', 'idle', 'ready'}
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
        forms.extend(f'{prefix} {noun}' for noun in ('terminal', 'window', 'codex'))
    for name in dict.fromkeys(names):
        if not name or len(name) > 180:
            continue
        forms.extend((name, f'{name} terminal', f'{name} window'))
        if len(pieces) >= 2:
            forms.extend((f'{name} codex', f'codex {name}'))
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
    for client in (context or {}).get('clients', []):
        if not isinstance(client, dict):
            continue
        if (client.get('class', '').lower() not in TERMINAL_CLASSES
                or not client.get('mapped', True)
                or not re.fullmatch(r'0x[0-9a-fA-F]+', client.get('address', ''))
                or not client.get('stableId') or not client.get('pid')):
            continue
        label, forms = window_names(client.get('title') or '')
        if not forms:
            continue
        identity = json.dumps([client['stableId'], client['address'], client['pid'], client['class']])
        key = hashlib.sha256(identity.encode()).hexdigest()[:20]
        if key in targets:
            continue
        targets[key] = dict(client, voice_label=label)
        words.append(Word(key, label, forms))
    # Identical project names are deliberately retained as competing meanings.
    expansions = compile_grammar(WINDOW_RULES, {'window': tuple(words)},
        {rule.intent_type: {name: tuple(targets) if value == '$window' else (value,)
                           for name, value in rule.arguments}
         for rule in WINDOW_RULES}, allow_ambiguous=True) if words else ()
    revision = hashlib.sha256(json.dumps([(w.id, w.forms) for w in words]).encode()).hexdigest()[:16]
    return WindowVocabulary(tuple(words), expansions, targets, revision)


def live_windows():
    result = subprocess.run(['hyprctl', 'clients', '-j'], capture_output=True, text=True, timeout=2)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'Could not read open windows')
    return inject_windows({'clients': json.loads(result.stdout)})
