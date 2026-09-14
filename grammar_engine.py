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


def compile_grammar(rules, vocabulary, schemas):
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
                for forms in product(*(word.forms for word in words)):
                    substitutions = dict(zip(slots, forms))
                    phrase = normalize(SLOT.sub(lambda match: substitutions[match[1]], pattern))
                    if not phrase:
                        raise ValueError(f"Empty pattern in {rule.id}")
                    meaning = (intent, command)
                    if phrase in phrases and phrases[phrase] != meaning:
                        raise ValueError(f"Conflicting phrase: {phrase}")
                    phrases[phrase] = meaning
                    expansions.append(Expansion(phrase, rule.id, pattern, tuple(sorted(ids.items())),
                                                intent, command, label))
    return tuple(expansions)
