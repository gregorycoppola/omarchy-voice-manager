"""Exact intent aliases and confidence-filtered fuzzy matching; no extra model."""
from difflib import SequenceMatcher
from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile

from command_catalog import GRAMMAR, INTENTS, EXPANSIONS, STRUCTURED_INTENTS, GRAMMAR_REVISION
from grammar_engine import Intent, normalize


@dataclass(frozen=True)
class Candidate:
    command: str
    intent: Intent
    phrase: str
    score: float
    source: str

    def to_dict(self):
        return {"intent": self.intent.to_dict(), "matched_phrase": self.phrase,
                "similarity": round(self.score, 4), "source": self.source,
                "rules": list(dict.fromkeys(e.rule_id for e in EXPANSIONS
                                             if e.phrase == self.phrase and e.intent == self.intent)),
                "expansions": [{"rule": e.rule_id, "pattern": e.pattern, "bindings": dict(e.bindings)}
                               for e in EXPANSIONS if e.phrase == self.phrase and e.intent == self.intent]}


@dataclass(frozen=True)
class ParseResult:
    text: str
    status: str
    method: str | None = None
    selected: Candidate | None = None
    candidates: tuple[Candidate, ...] = ()
    reason: str | None = None

    @property
    def intent(self):
        return self.selected.intent if self.selected else None

    @property
    def command(self):
        return self.selected.command if self.selected else None

    def to_dict(self):
        return {"text": self.text, "normalized": normalize(self.text), "status": self.status,
                "grammar_revision": GRAMMAR_REVISION,
                "method": self.method, "intent": self.intent.to_dict() if self.intent else None,
                "reason": self.reason, "candidates": [c.to_dict() for c in self.candidates]}


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
        result = self.parse(text)
        return result.command if result.method == "fuzzy" else None

    def parse(self, text):
        """Inspect a command without executing it or learning from the preview."""
        phrase = normalize(text)
        exact = self.exact(text)
        if exact:
            source = "grammar" if phrase in GRAMMAR else "alias"
            candidate = Candidate(exact, STRUCTURED_INTENTS[exact], phrase, 1.0, source)
            return ParseResult(text, "matched", "exact" if source == "grammar" else "alias",
                               candidate, (candidate,))
        # Avoid proposing actions for explicit negation or long dictation.
        if not 2 <= len(phrase.split()) <= 8 or set(phrase.replace("’", "'").split()) & {"no", "not", "never", "don't", "dont", "cancel"}:
            return ParseResult(text, "unrecognized", reason="Fuzzy matching skipped: negation or phrase length.")
        scores = {}
        for wording, command in (self.aliases | GRAMMAR).items():
            intent = STRUCTURED_INTENTS[command]
            score = SequenceMatcher(None, phrase, wording).ratio()
            if intent not in scores or score > scores[intent].score:
                scores[intent] = Candidate(command, intent, wording, score,
                                          "grammar" if wording in GRAMMAR else "alias")
        ranked = tuple(sorted(scores.values(), key=lambda c: c.score, reverse=True))
        if not ranked or ranked[0].score < .72:
            return ParseResult(text, "unrecognized", candidates=ranked[:5], reason="No candidate reaches 0.72 similarity.")
        if len(ranked) > 1 and ranked[0].score - ranked[1].score < .06:
            return ParseResult(text, "ambiguous", candidates=ranked[:5], reason="Competing meanings are less than 0.06 apart.")
        return ParseResult(text, "matched", "fuzzy", ranked[0], ranked[:5])

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
