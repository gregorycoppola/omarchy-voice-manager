"""Explicit picker verbs over individually identified captured windows."""
import re
from grammar_engine import Intent, normalize
from window_vocabulary import inject_windows

VERBS = ('close', 'minimize', 'maximize', 'focus', 'show', 'move')


def targets(context):
    vocabulary = inject_windows(context)
    rows = []
    active = (context or {}).get('active', {})
    if active.get('stableId') and active.get('pid') and active.get('address'):
        rows.append(('this window', active, 'current'))
    used = {'this window'}
    counts = {}
    for target in vocabulary.targets.values():
        name = normalize(target.get('voice_label') or target.get('class') or 'window')
        counts[name] = counts.get(name, 0) + 1
    for key, target in vocabulary.targets.items():
        label = target.get('voice_label') or target.get('class') or 'window'
        title = (target.get('title') or '').strip()
        if counts.get(normalize(label), 0) > 1 and title and normalize(title) != normalize(label):
            label += ' — ' + title[:80]
        label = normalize(label)
        if label in used:
            label += ' — ' + key[:8]
        used.add(label)
        rows.append((label, target, key))
    return rows


def destinations(context):
    workspaces = set(range(1, 11))
    for client in (context or {}).get('clients', []):
        number = client.get('workspace', {}).get('id')
        if type(number) is int and number > 0:
            workspaces.add(number)
    result = [dict(text=f'Workspace {n}', suffix=f'workspace {n}') for n in sorted(workspaces)]
    monitors = (context or {}).get('monitors', [])
    for monitor in monitors:
        name = monitor.get('name', '')
        if monitor.get('disabled') or not name:
            continue
        label = 'Laptop monitor' if name.startswith(('eDP', 'LVDS', 'DSI')) else 'External monitor'
        label += ' — ' + name
        result.append(dict(text=label, suffix='monitor ' + name))
    return result


def suggestions(context):
    places = destinations(context)
    result = []
    for label, target, key in targets(context):
        for verb in VERBS:
            text = f'{verb} {label}'
            row = dict(command=f'picker:{verb}:{key}', text=text, forms=[text], pickerWindow=True)
            if verb == 'move':
                row['destinations'] = places
            result.append(row)
    windows = pair_targets(context)
    if len(windows) >= 2:
        result.append(dict(command='picker:tile-pair', text='tile two specific windows',
                           forms=['tile two specific windows', 'tile two windows'],
                           tileWindows=[dict(id=key, label=label) for label, _, key in windows]))
    return result


def pair_targets(context):
    """One named row per captured window; omit the duplicate current-window alias."""
    return [(label, target, key) for label, target, key in targets(context) if key != 'current']


def parse_pair(text, context):
    from intent_matching import Candidate, ParseResult
    phrase = normalize(text)
    if not phrase.startswith('tile '):
        return None
    windows = pair_targets(context)
    by_label = {label: (target, key) for label, target, key in windows}
    matches = []
    for label, target, first in windows:
        prefix = 'tile ' + label + ' and '
        if not phrase.startswith(prefix):
            continue
        second = by_label.get(phrase[len(prefix):])
        if second and first != second[1]:
            matches.append((first, second[1]))
    if len(matches) != 1:
        return None
    first, second = matches[0]
    intent = Intent('picker_tile_pair', (('first', first), ('second', second)))
    candidate = Candidate(f'picker:tile-pair:{first}:{second}', intent, phrase, 1.0, 'picker', text)
    return ParseResult(text, 'matched', 'exact', candidate, (candidate,))


def parse(text, context):
    """Exact visible wording wins over legacy fuzzy/alias interpretations."""
    from intent_matching import Candidate, ParseResult
    phrase = normalize(text)
    pair = parse_pair(text, context)
    if pair is not None:
        return pair
    verb, _, tail = phrase.partition(' ')
    if verb not in VERBS:
        return None
    for label, target, key in targets(context):
        destination = None
        if tail != label:
            if verb != 'move' or not tail.startswith(label + ' to '):
                continue
            destination = tail[len(label) + 4:]
        if verb == 'move' and destination is None:
            continue
        args = [('window', key)]
        if destination is not None:
            match = re.fullmatch(r'workspace ([1-9][0-9]{0,8})', destination)
            if match:
                args.append(('workspace', match[1]))
            else:
                monitor = next((m for m in (context or {}).get('monitors', [])
                                if destination == normalize('monitor ' + m.get('name', ''))), None)
                if not monitor:
                    continue
                args.extend([('monitor', monitor['name']),
                             ('workspace', str(monitor.get('activeWorkspace', {}).get('id', 0)))])
        if verb == 'show':
            args.append(('workspace', str((context or {}).get('active', {}).get('workspace', {}).get('id', 0))))
        intent = Intent('picker_' + verb, tuple(args))
        command = f'picker:{verb}:{key}' + (':' + destination if destination else '')
        candidate = Candidate(command, intent, phrase, 1.0, 'picker', text)
        return ParseResult(text, 'matched', 'exact', candidate, (candidate,))
    return None


def resolve_target(context, key):
    return next((target for _, target, identity in targets(context) if identity == key), None)
