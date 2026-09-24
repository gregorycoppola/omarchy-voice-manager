"""Skipper adapter views of the external intent dataset. No authored wording lives here."""
from dataset_source import PROVIDER, DATASET_REVISION
from grammar_engine import Rule, Word, compile_grammar


def load_rule(row):
    return Rule(row['id'], tuple(row['patterns']), row['intent_type'],
                tuple(tuple(item) for item in row['arguments']), row['command'],
                row['label'], row.get('scope', 'global'))


TERMINAL_CLASSES = set(PROVIDER['terminal_classes'])
SITES = PROVIDER['sites']
APPS = {key: dict(value, classes=set(value['classes']),
                  desktop_files=tuple(value['desktop_files']))
        for key, value in PROVIDER['apps'].items()}
VOCABULARY = {name: tuple(Word(word['id'], word['label'], tuple(word['forms']))
                          for word in words)
              for name, words in PROVIDER['vocabulary'].items()}
BROWSER = VOCABULARY['browser'][0]
APP_WORDS = VOCABULARY['app']
SCHEMAS = {name: {key: tuple(values) for key, values in arguments.items()}
           for name, arguments in PROVIDER['executor_schemas'].items()}
RULES = tuple(load_rule(row) for row in PROVIDER['rules'])
WINDOW_RULES = tuple(load_rule(row) for row in PROVIDER['window_rules'])
INSTALLED_APP_RULES = tuple(load_rule(row) for row in PROVIDER['installed_app_rules'])
MOVE_PATTERNS = next(rule.patterns for rule in WINDOW_RULES if rule.id == 'move_named_window')
EXACT_ONLY_COMMANDS = set(PROVIDER['exact_only_commands'])
NO_LEARN_COMMANDS = set(PROVIDER['no_learn_commands'])

EXPANSIONS = compile_grammar(RULES, VOCABULARY, SCHEMAS)
# Compatibility views keep current execution IDs and version-1 learned aliases working.
INTENTS = {}
GRAMMAR = {}
STRUCTURED_INTENTS = {}
for expansion in EXPANSIONS:
    existing = STRUCTURED_INTENTS.setdefault(expansion.command, expansion.intent)
    if existing != expansion.intent:
        raise ValueError(f"Conflicting execution ID: {expansion.command}")
    entry = INTENTS.setdefault(expansion.command, {"label": expansion.label, "phrases": []})
    if expansion.phrase not in entry["phrases"]:
        entry["phrases"].append(expansion.phrase)
    GRAMMAR[expansion.phrase] = expansion.command

# Compatibility execution IDs remain adapter details, defined by the dataset.
for alias, target in PROVIDER['compatibility_aliases'].items():
    STRUCTURED_INTENTS[alias] = STRUCTURED_INTENTS[target]
    INTENTS[alias] = {'label': INTENTS[target]['label'], 'phrases': []}

GRAMMAR_REVISION = DATASET_REVISION
