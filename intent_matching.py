"""Exact intent aliases and confidence-filtered fuzzy matching; no extra model."""
from difflib import SequenceMatcher
import json
import os
from pathlib import Path
import tempfile

from command_catalog import GRAMMAR, INTENTS


def normalize(text):
    return " ".join(text.lower().split()).strip(" .!?")


class IntentMatcher:
    def __init__(self, path):
        self.path = Path(path)
        self.aliases = {}
        self.error = None
        try:
            data = json.loads(self.path.read_text())
            if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("aliases"), dict):
                raise ValueError("Invalid alias file format")
            for phrase, intent in data["aliases"].items():
                if not isinstance(intent, str) or intent not in INTENTS or not phrase or normalize(phrase) != phrase:
                    raise ValueError("Invalid phrase or intent in alias file")
                if phrase in GRAMMAR and GRAMMAR[phrase] != intent:
                    raise ValueError("Alias conflicts with a built-in command")
            self.aliases = data["aliases"]
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as exc:
            self.error = f"Could not load learned phrases: {exc}"

    def exact(self, text):
        phrase = normalize(text)
        return GRAMMAR.get(phrase) or self.aliases.get(phrase)

    def suggest(self, text):
        phrase = normalize(text)
        if not phrase or self.exact(phrase):
            return None
        # Avoid proposing actions for explicit negation or long dictation.
        if not 2 <= len(phrase.split()) <= 8 or set(phrase.replace("’", "'").split()) & {"no", "not", "never", "don't", "dont", "cancel"}:
            return None
        scores = {}
        for candidate, intent in (GRAMMAR | self.aliases).items():
            score = SequenceMatcher(None, phrase, candidate).ratio()
            scores[intent] = max(scores.get(intent, 0), score)
        ranked = sorted(scores, key=lambda intent: scores[intent], reverse=True)
        best = ranked[0]
        # Different phrases for the same intent are grouped before checking ambiguity.
        if scores[best] < .72 or (len(ranked) > 1 and scores[best] - scores[ranked[1]] < .06):
            return None
        return best

    def _save(self, aliases):
        if self.error:
            raise ValueError(self.error)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        name = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=self.path.parent, delete=False) as handle:
                name = Path(handle.name)
                json.dump({"version": 1, "aliases": aliases}, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            name.replace(self.path)
        finally:
            if name is not None:
                name.unlink(missing_ok=True)
        self.aliases = aliases

    def learn(self, text, intent):
        phrase = normalize(text)
        if not phrase or intent not in INTENTS:
            raise ValueError("Unknown intent or empty phrase")
        existing = self.exact(phrase)
        if existing and existing != intent:
            raise ValueError("Phrase already belongs to another intent")
        self._save(self.aliases | {phrase: intent})

    def forget(self, phrase):
        self._save({key: value for key, value in self.aliases.items() if key != phrase})
