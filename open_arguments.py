"""Optional launch arguments shared by written commands and the picker."""
from dataclasses import replace
import re

from command_catalog import APPS
from grammar_engine import normalize
from intent_matching import Candidate, ParseResult
from installed_apps import configured_terminal_id


def supports_open(command):
    return command in {'browser', 'terminal:new', *APPS} or command.startswith('desktop-app:')


def parse_open(text, matcher, expansions=()):
    phrase = normalize(text)
    if not phrase.startswith(('open ', 'launch ')):
        return None
    base = phrase
    tiled = False
    tile = re.search(r' and tile(?: it)?$', base)
    if tile:
        tiled = True
        base = base[:tile.start()]
    workspace = 'current'
    destination = re.search(r' in (?:this workspace|workspace ([1-9][0-9]{0,8}))$', base)
    if destination:
        workspace = destination.group(1) or 'current'
        base = base[:destination.start()]
    matches = [e for e in expansions if e.phrase == base and e.intent.type == 'open_installed_app']
    if len({e.command for e in matches}) == 1:
        e = matches[0]
        candidate = Candidate(e.command, e.intent, base, 1.0, 'installed', e.label, (e,))
        result = ParseResult(text, 'matched', 'exact', candidate, (candidate,))
    else:
        result = matcher.parse(base, expansions, use_corrections=False)
        if (tile and not destination and result.method == 'exact'
                and result.intent.type == 'open_browser_fullscreen'):
            return None  # Preserve the legacy authored browser-and-tile command.
        if result.command and supports_open(result.command) and result.command != 'terminal:new':
            return ParseResult(text, 'unrecognized', reason='Choose an installed app by its name.')
    if result.method == 'exact' and result.command and supports_open(result.command):
        if result.command == 'terminal:new':
            terminal_id = configured_terminal_id()
            if not any(e.command == 'desktop-app:' + str(terminal_id) for e in expansions):
                return ParseResult(text, 'unrecognized', reason='No installed default terminal is available.')
        options = dict(workspace=workspace, tile=tiled)
        return replace(result, text=text, launch_options=options)
    # Never let a malformed optional clause fuzzy-match an unrelated action.
    if destination or tile or re.search(r'\b(?:workspace|and tile)\b', phrase):
        return ParseResult(text, 'unrecognized', reason='Choose a supported app and a positive workspace number.')
    return None
