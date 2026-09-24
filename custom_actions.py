"""Explicit named phrases mapped to existing typed commands, stored outside Git."""
import personal_store
from pathlib import Path
import re
from uuid import uuid4

from command_catalog import GRAMMAR, STRUCTURED_INTENTS
from grammar_engine import normalize
from dataset_source import PROVIDER

# Compatibility IDs without authored phrases are not selectable actions.
COMMANDS = frozenset(GRAMMAR.values())


class CustomActions:
    def __init__(self, path):
        self.path = Path(path)
        self.actions = {}
        self.error = None
        try:
            data = personal_store.load(self.path)
            if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('actions'), dict):
                raise ValueError('Invalid custom actions format')
            self.validate(data['actions'])
            self.actions = data['actions']
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self.error = f'Could not load custom actions: {exc}'

    @staticmethod
    def validate(actions):
        phrases = set()
        for key, action in actions.items():
            if not re.fullmatch(r'[a-f0-9]{32}', key) or not isinstance(action, dict):
                raise ValueError('Invalid action identifier')
            name, phrase, command = (action.get(k) for k in ('name', 'phrase', 'command'))
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
                raise ValueError('Enter a name up to 100 characters')
            if not isinstance(phrase, str) or not 1 <= len(phrase) <= 200 or normalize(phrase) != phrase:
                raise ValueError('Enter a phrase up to 200 characters')
            if set(phrase.replace('’', "'").split()) & {'no', 'not', 'never', "don't", 'dont', 'cancel'}:
                raise ValueError('Use a positive phrase without cancellation words')
            if phrase in GRAMMAR or phrase in {normalize(row['text']) for row in PROVIDER['approved_aliases']} or phrase in phrases or re.match(r'tile .*\band\b', phrase):
                raise ValueError('That phrase is already reserved; choose a distinct phrase')
            if not isinstance(command, str) or command not in COMMANDS:
                raise ValueError('Choose a supported action')
            if action.get('intent') != STRUCTURED_INTENTS[command].to_dict():
                raise ValueError('The saved action changed meaning; review the saved personal action before continuing')
            if action.get('canonical_plan', STRUCTURED_INTENTS[command].canonical_plan()) != STRUCTURED_INTENTS[command].canonical_plan():
                raise ValueError('Saved action changed canonical meaning; review personal overrides')
            phrases.add(phrase)

    def _write(self, actions):
        if self.error:
            raise ValueError(self.error)
        self.validate(actions)
        personal_store.save(self.path, {'version': 1, 'actions': actions})
        self.actions = actions

    def save(self, name, phrase, command, key=None):
        phrase = normalize(phrase)
        for filename, section in [('aliases.json', 'aliases'), ('corrections.json', 'rules')]:
            path = self.path.with_name(filename)
            try:
                data = personal_store.load(path)
            except FileNotFoundError:
                data = {}
            if phrase in data.get(section, {}):
                raise ValueError('That phrase already has a learned meaning or correction')
        if command not in COMMANDS:
            raise ValueError('Choose a supported action')
        if key is not None and key not in self.actions:
            raise ValueError('That action no longer exists; refresh the list')
        key = key or uuid4().hex
        self._write(self.actions | {key: dict(name=name.strip(), phrase=phrase, command=command,
                                             intent=STRUCTURED_INTENTS[command].to_dict(),
                                             canonical_plan=STRUCTURED_INTENTS[command].canonical_plan())})
        return key

    def remove(self, key):
        self._write({k: v for k, v in self.actions.items() if k != key})
