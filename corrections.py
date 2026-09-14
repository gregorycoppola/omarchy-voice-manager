"""Explicit, reversible phrase corrections; independent of automatic aliases."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile

from command_catalog import STRUCTURED_INTENTS
from grammar_engine import normalize


class Corrections:
    def __init__(self, path):
        self.path = Path(path)
        self.rules = {}
        self.events = []
        self.error = None
        try:
            data = json.loads(self.path.read_text())
            if data.get('version') != 1 or not isinstance(data.get('rules'), dict) or not isinstance(data.get('events'), list):
                raise ValueError('Invalid corrections file')
            for phrase, rule in data['rules'].items():
                if not phrase or normalize(phrase) != phrase or not isinstance(rule, dict):
                    raise ValueError('Invalid corrected phrase')
                if not isinstance(rule.get('meant'), str) or not rule['meant'].strip() or rule.get('command') not in STRUCTURED_INTENTS:
                    raise ValueError('Invalid correction intent or words')
            self.rules, self.events = data['rules'], data['events']
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            self.error = f'Could not load corrections: {exc}'

    def save(self, heard, meant, command, recording=None):
        phrase = normalize(heard)
        if not phrase or not meant.strip() or command not in STRUCTURED_INTENTS:
            raise ValueError('Enter the words you meant and choose an intended action.')
        rule = dict(heard=heard, meant=meant.strip(), command=command,
                    intent=STRUCTURED_INTENTS[command].to_dict(), recording=recording,
                    updated_at=datetime.now(timezone.utc).isoformat())
        self._write(self.rules | {phrase: rule}, dict(action='save', phrase=phrase,
                    previous=self.rules.get(phrase), correction=rule))

    def forget(self, heard):
        phrase = normalize(heard)
        self._write({key: value for key, value in self.rules.items() if key != phrase},
                    dict(action='remove', phrase=phrase, previous=self.rules.get(phrase)))

    def _write(self, rules, event):
        if self.error:
            raise ValueError(self.error)
        event['timestamp'] = datetime.now(timezone.utc).isoformat()
        events = self.events + [event]
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', dir=self.path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(dict(version=1, rules=rules, events=events), stream, ensure_ascii=False, indent=2)
                stream.write('\n')
            temporary.replace(self.path)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
        self.rules, self.events = rules, events
