"""Finite, typed command grammars. No UI, speech model, or execution imports."""
from dataclasses import dataclass
from itertools import product
import re


def normalize(text):
    return " ".join(text.lower().split()).strip(" .!?")


@dataclass(frozen=True)
class Intent:
    type: str
    arguments: tuple[tuple[str, str], ...] = ()

    def to_dict(self):
        return {"schema_version": 1, "type": self.type, "arguments": dict(self.arguments)}

    def canonical_plan(self):
        """Provider-neutral intent instances, validated by the external catalog."""
        from dataset_source import CATALOG
        if self.type == 'tile_workspace':
            args = dict(self.arguments)
            category = args['category']
            return CATALOG.validate_plan([{'intent': 'window.tile', 'arguments': {
                'scope': 'open_windows' if category == 'windows' else category,
                'other_windows': 'preserve' if category == 'windows' else 'hide',
                **({'workspace': int(args['workspace'])} if args['workspace'] != 'current' else {})}}])
        if self.type == 'picker_tile_pair':
            args = dict(self.arguments)
            return CATALOG.validate_plan([{'intent': 'window.tile_pair', 'arguments': {
                'first': {'kind': 'id', 'value': args['first']},
                'second': {'kind': 'id', 'value': args['second']},
                'other_windows': 'hide'}}])
        if self.type.startswith('picker_'):
            args = dict(self.arguments)
            target = {'kind': 'current'} if args['window'] == 'current' else {'kind': 'id', 'value': args['window']}
            verb = self.type.removeprefix('picker_')
            if verb in ('move', 'show'):
                plan = [{'intent': 'window.move_workspace', 'arguments': {
                    'target': target, 'workspace': {'kind': 'id', 'value': args['workspace']}}}]
                if verb == 'show':
                    plan.append({'intent': 'window.focus', 'arguments': {'target': target}})
            else:
                operation = {'minimize': 'hide'}.get(verb, verb)
                plan = [{'intent': 'window.' + operation, 'arguments': {'target': target}}]
            return CATALOG.validate_plan(plan)
        if self.type == 'move_named_window_workspace':
            args = dict(self.arguments)
            return CATALOG.validate_plan([{'intent': 'window.move_workspace', 'arguments': {
                'target': {'kind': 'id', 'value': args['window']},
                'workspace': {'kind': 'id', 'value': args['workspace']}}}])
        if self.type == 'switch_workspace':
            workspace = int(dict(self.arguments)['workspace'])
            return CATALOG.validate_plan([{'intent': 'workspace.switch',
                                           'arguments': {'workspace': workspace}}])
        return CATALOG.canonical_plan('skipper', self.type, dict(self.arguments))


@dataclass(frozen=True)
class Word:
    id: str
    label: str
    forms: tuple[str, ...]


@dataclass(frozen=True)
class Rule:
    id: str
    patterns: tuple[str, ...]
    intent_type: str
    # A $name binds a vocabulary ID; other strings are literal arguments.
    arguments: tuple[tuple[str, str], ...]
    command: str
    label: str
    scope: str = "global"


@dataclass(frozen=True)
class Expansion:
    phrase: str
    rule_id: str
    pattern: str
    bindings: tuple[tuple[str, str], ...]
    intent: Intent
    command: str
    label: str


SLOT = re.compile(r"<([a-z_]+)>")


def compile_grammar(rules, vocabulary, schemas, *, allow_ambiguous=False):
    """Validate and expand rules, rejecting conflicting phrase meanings."""
    for name, words in vocabulary.items():
        if not words or len({word.id for word in words}) != len(words):
            raise ValueError(f"Empty vocabulary or duplicate IDs: {name}")
        for word in words:
            if not word.id or not word.forms or any(not normalize(form) for form in word.forms):
                raise ValueError(f"Empty vocabulary entry: {name}/{word.id}")
    expansions, phrases, rule_ids = [], {}, set()
    for rule in rules:
        if not rule.id or rule.id in rule_ids:
            raise ValueError(f"Duplicate or empty rule ID: {rule.id}")
        rule_ids.add(rule.id)
        if rule.scope != "global":
            raise ValueError("Only global scope is supported in this version")
        if rule.intent_type not in schemas or not rule.patterns:
            raise ValueError(f"Unknown intent schema or empty rule: {rule.id}")
        for pattern in rule.patterns:
            slots = tuple(dict.fromkeys(SLOT.findall(pattern)))
            if any(slot not in vocabulary for slot in slots):
                raise ValueError(f"Unknown non-terminal in {rule.id}: {pattern}")
            if '<' in SLOT.sub('', pattern) or '>' in SLOT.sub('', pattern):
                raise ValueError(f"Invalid non-terminal in {rule.id}: {pattern}")
            for words in product(*(vocabulary[slot] for slot in slots)):
                ids = dict(zip(slots, (word.id for word in words)))
                labels = dict(zip(slots, (word.label for word in words)))
                try:
                    arguments = tuple(sorted((key, ids[value[1:]] if value.startswith('$') else value)
                                             for key, value in rule.arguments))
                    command = rule.command.format(**ids)
                    label = rule.label.format(**labels)
                except KeyError as exc:
                    raise ValueError(f"Unbound slot in {rule.id}: {exc}") from exc
                schema = schemas[rule.intent_type]
                if len(dict(arguments)) != len(arguments) or set(dict(arguments)) != set(schema):
                    raise ValueError(f"Invalid arguments for {rule.intent_type}")
                if any(value not in schema[key] for key, value in arguments):
                    raise ValueError(f"Unsupported argument value for {rule.intent_type}: {arguments}")
                intent = Intent(rule.intent_type, arguments)
                intent.canonical_plan()
                for forms in product(*(word.forms for word in words)):
                    substitutions = dict(zip(slots, forms))
                    phrase = normalize(SLOT.sub(lambda match: substitutions[match[1]], pattern))
                    if not phrase:
                        raise ValueError(f"Empty pattern in {rule.id}")
                    meaning = (intent, command)
                    if not allow_ambiguous and phrase in phrases and phrases[phrase] != meaning:
                        raise ValueError(f"Conflicting phrase: {phrase}")
                    phrases[phrase] = meaning
                    expansions.append(Expansion(phrase, rule.id, pattern, tuple(sorted(ids.items())),
                                                intent, command, label))
    return tuple(expansions)
