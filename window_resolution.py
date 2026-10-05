"""Resolve intent slots against a frozen recording snapshot, one question at a time."""
from copy import deepcopy
from dataclasses import dataclass
import re

from command_catalog import APPS, TERMINAL_CLASSES
from grammar_engine import normalize
from window_vocabulary import window_names, inject_windows

BROWSERS = {'chromium', 'google-chrome', 'google-chrome-stable', 'chrome',
            'firefox', 'org.mozilla.firefox', 'brave-browser', 'brave',
            'vivaldi-stable', 'microsoft-edge'}


def identity(window):
    return tuple(window.get(k) for k in ('address', 'pid', 'class', 'stableId'))


@dataclass(frozen=True)
class WindowQuestion:
    slot: str
    reference: str
    candidates: tuple

    @property
    def prompt(self):
        if self.reference == 'the browser':
            return 'Which browser window do you mean?'
        if self.slot == 'window':
            return f'Which {self.reference.removeprefix("the ")} window do you mean?'
        return f'Which {self.slot} window do you mean by “{self.reference}”?'


def needs_window_resolution(intent):
    return bool(intent and (intent.type in ('tile_pair', 'tile_current_window_with_browser',
                    'open_browser_and_tile', 'open_browser_fullscreen', 'close_browser_tabs', 'hide_application', 'show_application')
                or (intent.type == 'close_window' and dict(intent.arguments)['application'] != 'terminal')))


class WindowResolution:
    def __init__(self, intent, context):
        self.intent = intent
        self.references = intent.arguments
        if intent.type in ('close_window', 'hide_application', 'show_application'):
            application = dict(intent.arguments)['application']
            reference = {'browser': 'the browser', 'files': 'the file browser',
                         'x': 'X', 'discord': 'Discord', 'tensaku': 'Tensaku', 'chrome': 'Chrome'}[application]
            self.references = (('window', reference),)
        self.context = deepcopy(context or {})
        self.resolved = {}
        self.windows = tuple(c for c in self.context.get('clients', [])
            if c.get('mapped', True) and c.get('pid') and c.get('stableId')
            and re.fullmatch(r'0x[0-9a-fA-F]+', c.get('address', ''))
            and 'io.github.gregorycoppola.Skipper' not in (c.get('class'), c.get('initialClass')))

    def candidates(self, reference):
        name = normalize(reference)
        if name in ('this window', 'the current window', 'current window'):
            active = self.context.get('active', {})
            return tuple(c for c in self.windows if identity(c) == identity(active))
        name = name.removeprefix('the ')
        if name in ('browser', 'chrome', 'chromium', 'firefox'):
            classes = BROWSERS if name == 'browser' else ({'firefox', 'org.mozilla.firefox'} if name == 'firefox' else {'chromium', 'google-chrome', 'google-chrome-stable', 'chrome'})
            matches = tuple(c for c in self.windows if c.get('class', '').lower() in classes)
            # Resolve generic browser references from the recording snapshot.
            # Missing visibility metadata must not silently exclude candidates.
            if name == 'browser' and self.intent.type not in ('show_application', 'show_all_application') and all(type(c.get('visible')) is bool for c in matches):
                visible = tuple(c for c in matches if c['visible'] and not c.get('hidden', False))
                if visible:
                    return visible
            return matches
        app = {'file browser': 'files', 'file manager': 'files', 'files': 'files',
               'x': 'x', 'twitter': 'x', 'discord': 'discord',
               'tensaku': 'tensaku', 'image viewer': 'tensaku'}.get(name)
        if app:
            return tuple(c for c in self.windows if c.get('class') in APPS[app]['classes'])
        if name == 'terminal':
            return tuple(c for c in self.windows if c.get('class', '').lower() in TERMINAL_CLASSES)
        if not hasattr(self, '_window_vocabulary'):
            self._window_vocabulary = inject_windows(self.context)
        named = {identity(self._window_vocabulary.targets[word.id]) for word in self._window_vocabulary.words
                 if name in word.forms}
        if named:
            return tuple(c for c in self.windows if identity(c) in named)
        return tuple(c for c in self.windows if name in window_names(c.get('title', ''))[1])

    def advance(self):
        for slot, reference in self.references:
            if slot in self.resolved:
                continue
            candidates = self.candidates(reference)
            if not candidates:
                raise RuntimeError(f'No open window matches “{reference}”. Please start a new command.')
            if len(candidates) > 1:
                return WindowQuestion(slot, reference, candidates)
            self.resolved[slot] = candidates[0]
        if len({identity(c) for c in self.resolved.values()}) != len(self.resolved):
            raise RuntimeError('Both references name the same window. Please name two different windows.')
        return None

    def choose(self, question, index):
        current = self.advance()
        if current != question or not 0 <= index < len(question.candidates):
            raise ValueError('That window choice is no longer available')
        self.resolved[question.slot] = question.candidates[index]
