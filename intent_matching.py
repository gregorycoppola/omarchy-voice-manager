"""Exact intent aliases and confidence-filtered fuzzy matching; no extra model."""
import personal_store
from difflib import SequenceMatcher
from dataclasses import dataclass
import json
import re
from pathlib import Path

from command_catalog import GRAMMAR, INTENTS, EXPANSIONS, STRUCTURED_INTENTS, GRAMMAR_REVISION, EXACT_ONLY_COMMANDS, NO_LEARN_COMMANDS
from grammar_engine import Intent, normalize
from corrections import Corrections
from custom_actions import CustomActions
from intent_dataset_aliases import load_approved_aliases
from dataset_source import CATALOG, DATASET_REVISION, PROVIDER


@dataclass(frozen=True)
class Candidate:
    command: str
    intent: Intent
    phrase: str
    score: float
    source: str
    label: str = ""
    evidence: tuple = ()

    def to_dict(self):
        return {"intent": self.intent.to_dict(), "label": self.label, "matched_phrase": self.phrase,
                "canonical_plan": self.intent.canonical_plan(),
                "similarity": round(self.score, 4), "source": self.source,
                "rules": list(dict.fromkeys(e.rule_id for e in self.evidence
                                             if e.phrase == self.phrase and e.intent == self.intent)),
                "expansions": [{"rule": e.rule_id, "pattern": e.pattern, "bindings": dict(e.bindings)}
                               for e in self.evidence if e.phrase == self.phrase and e.intent == self.intent]}


@dataclass(frozen=True)
class ParseResult:
    text: str
    status: str
    method: str | None = None
    selected: Candidate | None = None
    candidates: tuple[Candidate, ...] = ()
    reason: str | None = None
    correction: dict | None = None
    launch_options: dict | None = None

    @property
    def intent(self):
        return self.selected.intent if self.selected else None

    @property
    def command(self):
        return self.selected.command if self.selected else None

    @property
    def canonical_plan(self):
        return self.intent.canonical_plan() if self.intent else []

    def to_dict(self):
        return {"text": self.text, "normalized": normalize(self.text), "status": self.status,
                "catalog_revision": DATASET_REVISION, "canonical_plan": self.canonical_plan,
                "grammar_revision": GRAMMAR_REVISION,
                "method": self.method, "intent": self.intent.to_dict() if self.intent else None,
                "reason": self.reason, "correction": self.correction,
                "launch_options": self.launch_options,
                "candidates": [c.to_dict() for c in self.candidates]}


class IntentMatcher:
    def __init__(self, path):
        self.path = Path(path)
        self.aliases = {}
        self.error = None
        self.dataset_aliases = {}
        self.dataset_error = None
        try:
            self.dataset_aliases = load_approved_aliases()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.dataset_error = f"Could not load reviewed dataset phrases: {exc}"
        try:
            data = personal_store.load(self.path)
            if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("aliases"), dict):
                raise ValueError("Invalid alias file format")
            for phrase, intent in data["aliases"].items():
                if not isinstance(intent, str) or intent not in INTENTS or not phrase or normalize(phrase) != phrase:
                    raise ValueError("Invalid phrase or intent in alias file")
                if phrase in GRAMMAR and GRAMMAR[phrase] != intent:
                    raise ValueError("Alias conflicts with a built-in command")
                if phrase in self.dataset_aliases and self.dataset_aliases[phrase] != intent:
                    raise ValueError("Alias conflicts with a reviewed dataset command")
            for phrase, plan in data.get('canonical_plans', {}).items():
                if phrase in data['aliases'] and STRUCTURED_INTENTS[data['aliases'][phrase]].canonical_plan() != plan:
                    raise ValueError('Saved alias changed meaning; review personal overrides')
            self.aliases = {phrase: command for phrase, command in data["aliases"].items()
                            if command not in NO_LEARN_COMMANDS}
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as exc:
            self.error = f"Could not load learned phrases: {exc}"

    def exact(self, text):
        phrase = normalize(text)
        return GRAMMAR.get(phrase) or self.dataset_aliases.get(phrase) or self.aliases.get(phrase)

    def suggest(self, text):
        result = self.parse(text)
        return result.command if result.method == "fuzzy" else None

    def parse_instance(self, instance, extra_expansions=()):
        """Adapt validated LLM/API output only when an installed binding matches it.

        This does not execute anything. The runtime's normal target resolution
        and confirmation flow is still required for the returned candidate.
        """
        CATALOG.validate_instance(instance)
        matches = {}
        for expansion in EXPANSIONS + tuple(extra_expansions):
            plan = expansion.intent.canonical_plan()
            if plan == [instance]:
                matches.setdefault(expansion.intent, Candidate(
                    expansion.command, expansion.intent, expansion.phrase, 1.0,
                    'structured', expansion.label, (expansion,)))
        if len(matches) == 1:
            candidate = next(iter(matches.values()))
            return ParseResult('', 'matched', 'structured', candidate, (candidate,))
        return ParseResult('', 'ambiguous' if matches else 'unrecognized',
                           candidates=tuple(matches.values()),
                           reason='No unique installed executor binding for these arguments.')

    def parse(self, text, extra_expansions=(), *, use_corrections=True):
        """Parse one snapshot, retaining competing dynamic slot bindings."""
        phrase = normalize(text)
        custom = CustomActions(self.path.with_name('actions.json'))
        if custom.error:
            return ParseResult(text, 'unrecognized', reason=custom.error)
        corrections = Corrections(self.path.with_name('corrections.json'))
        if corrections.error:
            return ParseResult(text, 'unrecognized', reason=corrections.error)
        correction = corrections.rules.get(phrase) if use_corrections else None
        if correction:
            if correction.get('kind') == 'wording':
                # Resolve relative references against this recording's windows, not
                # the old correction session. Do not chain rules or fuzzy guesses.
                resolved = self.parse(correction['meant'], extra_expansions, use_corrections=False)
                if resolved.method not in ('exact', 'alias') or not resolved.intent:
                    return ParseResult(text, 'unrecognized', reason='Saved wording no longer has a clear action.', correction=correction)
                saved_intent = correction['intent']
                if (saved_intent.get('type') == 'tile_pair'
                        and resolved.intent.type == 'tile_current_window_with_browser'
                        and saved_intent.get('arguments') == dict(resolved.intent.arguments)):
                    saved_intent = saved_intent | {'type': resolved.intent.type}
                if resolved.intent.type != saved_intent.get('type'):
                    return ParseResult(text, 'unrecognized', reason='Saved wording changed meaning; please correct it again.', correction=correction)
                if correction.get('command') in STRUCTURED_INTENTS and resolved.intent.to_dict() != saved_intent:
                    return ParseResult(text, 'unrecognized', reason='Saved action changed; please correct it again.', correction=correction)
                return ParseResult(text, 'matched', 'correction', resolved.selected, resolved.candidates,
                                   reason='Explicit wording correction, resolved against current windows.', correction=correction)
            command = correction['command']
            candidate = Candidate(command, STRUCTURED_INTENTS[command], correction['meant'],
                                  1.0, 'correction', INTENTS[command]['label'])
            return ParseResult(text, 'matched', 'correction', candidate, (candidate,),
                               reason='Exact phrase explicitly corrected by the user.', correction=correction)
        # Correct known browser misspellings only inside an otherwise exact
        # authored opening/tiling command. Do not fuzzy-match its action words.
        spelling = PROVIDER['language_policy']['browser_spelling']
        browser_spelling = re.sub(r'\b(?:' + '|'.join(re.escape(word) for word in spelling['forms']) + r')\b', spelling['replacement'], phrase)
        spelling_command = GRAMMAR.get(browser_spelling) if browser_spelling != phrase else None
        if spelling_command in spelling['commands']:
            intent = STRUCTURED_INTENTS[spelling_command]
            candidate = Candidate(spelling_command, intent, browser_spelling,
                                  SequenceMatcher(None, phrase, browser_spelling).ratio(), 'spelling',
                                  INTENTS[spelling_command]['label'],
                                  tuple(e for e in EXPANSIONS if e.phrase == browser_spelling and e.intent == intent))
            return ParseResult(text, 'matched', 'fuzzy', candidate, (candidate,),
                               reason='Browser spelling corrected within an exact command.')
        # Authored, specific intents take precedence over the generic pair frame.
        specific = GRAMMAR.get(phrase)
        if specific in PROVIDER['language_policy']['specific_before_free_text']:
            intent = STRUCTURED_INTENTS[specific]
            candidate = Candidate(specific, intent, phrase, 1.0, 'grammar', INTENTS[specific]['label'],
                                  tuple(e for e in EXPANSIONS if e.phrase == phrase and e.intent == intent))
            return ParseResult(text, 'matched', 'exact', candidate, (candidate,))
        if phrase not in GRAMMAR and not set(phrase.split()) & {"no", "not", "never", "don't", "dont", "cancel"}:
            for rule in PROVIDER['free_text_rules']:
                if rule.get('argument') != 'application':
                    continue
                for pattern in sorted(rule['patterns'], key=len, reverse=True):
                    match = re.fullmatch(re.escape(pattern).replace('<application>', '(.{1,80})'), phrase)
                    if not match:
                        continue
                    application = match[1].strip()
                    if not application:
                        continue
                    intent = Intent(rule['intent_type'], (('application', application),))
                    intent.canonical_plan()
                    candidate = Candidate(rule['command'].format(application=application), intent,
                                          phrase, 1.0, 'grammar', rule['label'])
                    return ParseResult(text, 'matched', 'exact', candidate, (candidate,))
        for rule in PROVIDER.get('numeric_rules', []):
            for pattern in rule['patterns']:
                match = re.fullmatch(re.escape(pattern).replace('<workspace>', r'([1-9][0-9]{0,8})'), phrase)
                if match and phrase not in GRAMMAR:
                    intent = Intent(rule['intent_type'], (('workspace', match[1]),))
                    intent.canonical_plan()
                    candidate = Candidate(rule['command'].format(workspace=match[1]), intent,
                                          phrase, 1.0, 'grammar', rule['label'])
                    return ParseResult(text, 'matched', 'exact', candidate, (candidate,))
        # Resolve named workspace destinations only from this capture's exact
        # focus vocabulary. Never fall back to moving the current window.
        named_workspace = re.fullmatch(r'move (.+) to workspace ([1-9][0-9]{0,8})', phrase)
        if named_workspace and phrase not in GRAMMAR:
            name, workspace = named_workspace.groups()
            matches = {}
            for expansion in extra_expansions:
                if expansion.intent.type != 'focus_window' or expansion.phrase != 'focus ' + name:
                    continue
                key = dict(expansion.intent.arguments)['window']
                intent = Intent('move_named_window_workspace', (('window', key), ('workspace', workspace)))
                intent.canonical_plan()
                matches[key] = Candidate(f'move-window-workspace:{key}:{workspace}', intent,
                    phrase, 1.0, 'window', f'Move {name} to workspace {workspace}')
            candidates = tuple(matches.values())
            if len(candidates) == 1:
                return ParseResult(text, 'matched', 'exact', candidates[0], candidates)
            return ParseResult(text, 'ambiguous' if candidates else 'unrecognized',
                               candidates=candidates, reason='Name one open window to move.')
        if phrase not in GRAMMAR and phrase.startswith('move ') and 'workspace' in phrase.split():
            return ParseResult(text, 'unrecognized', reason='Name a positive workspace number, for example “move this window to workspace 3”.')
        pair_rule = PROVIDER['free_text_rules'][0]
        pair_pattern = re.escape(pair_rule['pattern']).replace(r'<first>', '(.+?)').replace(r'<second>', '(.+)')
        pair = re.fullmatch(pair_pattern, phrase)
        if pair and not set(phrase.split()) & {"no", "not", "never", "don't", "dont", "cancel"}:
            intent = Intent(pair_rule['intent_type'], (('first', pair[1]), ('second', pair[2])))
            intent.canonical_plan()
            candidate = Candidate(pair_rule['command'], intent, phrase, 1.0, 'grammar', pair_rule['label'],
                                  tuple(e for e in EXPANSIONS if e.phrase == phrase and e.intent == intent))
            return ParseResult(text, 'matched', 'exact', candidate, (candidate,))
        # An incomplete pair must never fall back to tiling every window.
        if phrase.startswith('tile ') and 'and' in phrase.split():
            return ParseResult(text, 'unrecognized', reason='Name two windows to tile.')
        expansions = EXPANSIONS + tuple(extra_expansions)
        entries = []
        for wording, command in (self.aliases | GRAMMAR).items():
            intent = STRUCTURED_INTENTS[command]
            evidence = tuple(e for e in expansions if e.phrase == wording and e.intent == intent)
            entries.append(Candidate(command, intent, wording, 1.0,
                "grammar" if wording in GRAMMAR else "alias", INTENTS.get(command, {}).get('label', command), evidence))
        for wording, command in self.dataset_aliases.items():
            if command not in STRUCTURED_INTENTS:
                continue
            entries.append(Candidate(command, STRUCTURED_INTENTS[command], wording, 1.0,
                                     "dataset_approved", INTENTS[command]['label']))
        for action in custom.actions.values():
            command = action['command']
            entries.append(Candidate(command, STRUCTURED_INTENTS[command], action['phrase'],
                                     1.0, 'custom', action['name']))
        for expansion in extra_expansions:
            entries.append(Candidate(expansion.command, expansion.intent, expansion.phrase, 1.0,
                                     'installed_app' if expansion.command.startswith('desktop-app:') else 'window',
                                     expansion.label, (expansion,)))
        exact = {candidate.intent: candidate for candidate in entries if candidate.phrase == phrase}
        if len(exact) > 1:
            return ParseResult(text, 'ambiguous', candidates=tuple(exact.values()),
                               reason='This phrase names more than one meaning. Use a more specific window title.')
        if exact:
            candidate = next(iter(exact.values()))
            method = 'alias' if candidate.source in ('alias', 'custom') else 'exact'
            return ParseResult(text, 'matched', method, candidate, (candidate,))
        if phrase.split()[:1] == ['hide']:
            return ParseResult(text, 'unrecognized', reason='Hide commands require their exact built-in phrase.')
        if re.search(r'\bnon[ -]?terminals?\b', phrase):
            return ParseResult(text, 'unrecognized', reason='Use tile the apps for non-terminal windows.')
        # Keep the existing guards, allowing longer named-window titles when the
        # entire command matched exactly above.
        move_match = re.fullmatch(r'move (.+) to (?:the )?other \w+', phrase)
        named_move = move_match and move_match[1] not in ('window', 'the window', 'this window')
        if not 2 <= len(phrase.split()) <= (16 if named_move else 8) or set(phrase.replace("’", "'").split()) & {"no", "not", "never", "don't", "dont", "cancel"}:
            return ParseResult(text, "unrecognized", reason="Fuzzy matching skipped: negation or phrase length.")
        scores = {}
        # A named terminal request must never degrade into closing the most
        # recent terminal just because its name is absent or poorly recognized.
        named_close = re.fullmatch(r'close (?:the )?.+ (?:terminal|window|codex)', phrase)
        for candidate in entries:
            if candidate.command in EXACT_ONLY_COMMANDS or candidate.source in ('custom', 'installed_app'):
                continue
            if phrase.startswith('focus ') and candidate.intent.type != 'focus_window':
                continue
            if named_close and candidate.intent.type != 'close_named_window':
                continue
            if named_move and candidate.intent.type not in ('move_named_window', 'move_application'):
                continue
            score = SequenceMatcher(None, phrase, candidate.phrase).ratio()
            if candidate.source == 'window' or candidate.intent.type == 'move_application':
                if not candidate.evidence:
                    continue
                # Score both the frame and slot, including fuzzy frames. An
                # alternate article/frame must not bypass the name check.
                slot = '<window>' if candidate.source == 'window' else '<window_app>'
                prefix, suffix = candidate.evidence[0].pattern.split(slot)
                count = len(prefix.split())
                tokens = phrase.split()
                heard_prefix = ' '.join(tokens[:count])
                end = len(tokens) - len(suffix.split()) if suffix else len(tokens)
                heard_name = ' '.join(tokens[count:end])
                name = candidate.phrase[len(prefix):len(candidate.phrase) - len(suffix) if suffix else None]
                score = min(score, SequenceMatcher(None, heard_prefix, prefix.strip()).ratio(),
                            SequenceMatcher(None, heard_name, name).ratio())
                if suffix:
                    score = min(score, SequenceMatcher(None, ' '.join(tokens[end:]), suffix.strip()).ratio())
                if candidate.source == 'window':
                    # Shared window nouns must not make an unrelated short
                    # title look like a strong name match.
                    core = lambda value: re.sub(r'\s+(terminal|window|codex)$', '', value)
                    score = min(score, SequenceMatcher(None, core(heard_name), core(name)).ratio())
            if candidate.intent not in scores or score > scores[candidate.intent].score:
                scores[candidate.intent] = Candidate(candidate.command, candidate.intent,
                    candidate.phrase, score, candidate.source, candidate.label, candidate.evidence)
        ranked = tuple(sorted(scores.values(), key=lambda c: c.score, reverse=True))
        if not ranked or ranked[0].score < .72:
            return ParseResult(text, "unrecognized", candidates=ranked[:5], reason="No candidate reaches 0.72 similarity.")
        if len(ranked) > 1 and ranked[0].score - ranked[1].score < .06:
            return ParseResult(text, "ambiguous", candidates=ranked[:5], reason="Competing meanings are less than 0.06 apart.")
        return ParseResult(text, "matched", "fuzzy", ranked[0], ranked[:5])

    def _save(self, aliases):
        if self.error:
            raise ValueError(self.error)
        personal_store.save(self.path, {'version': 1, 'aliases': aliases,
                           'canonical_plans': {phrase: STRUCTURED_INTENTS[command].canonical_plan() for phrase, command in aliases.items()}})
        self.aliases = aliases

    def learn(self, text, intent):
        phrase = normalize(text)
        if not phrase or intent not in INTENTS:
            raise ValueError("Unknown intent or empty phrase")
        if intent in NO_LEARN_COMMANDS:
            raise ValueError("This command does not accept learned aliases; use a built-in phrase")
        custom = CustomActions(self.path.with_name('actions.json'))
        if custom.error:
            raise ValueError(custom.error)
        if any(a['phrase'] == phrase for a in custom.actions.values()):
            raise ValueError('Phrase belongs to a custom action')
        existing = self.exact(phrase)
        if existing and existing != intent:
            raise ValueError("Phrase already belongs to another intent")
        self._save(self.aliases | {phrase: intent})

    def forget(self, phrase):
        self._save({key: value for key, value in self.aliases.items() if key != phrase})
