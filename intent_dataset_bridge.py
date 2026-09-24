"""Read the external research dataset for parse-only Skipper comparison.

This module never returns an executable Skipper action. Source command IDs are
evidence labels only; the current grammar and runtime remain authoritative.
"""

from dataclasses import dataclass
import json
from pathlib import Path
import re

from grammar_engine import normalize
from dataset_source import CATALOG, DATASET_ROOT

DATA_ROOT = DATASET_ROOT / "data"
_ACTION = r"open|launch|tile|close|show|list|start|stop|set|turn|move|focus|switch|read|send|run|play|pause"
_BOUNDARY = re.compile(
    rf"\s*(?:\n+|;|\band\s+then\b|\bthen\b|\band\b(?=\s+(?:{_ACTION})\b))\s*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DatasetPhrase:
    intent: str
    variant: int
    text: str
    origin: str
    arguments: dict | None


@dataclass(frozen=True)
class DatasetPreview:
    text: str
    status: str
    clauses: tuple[str, ...] = ()
    phrases: tuple[DatasetPhrase, ...] = ()
    intent_ids: tuple[str, ...] = ()
    sequence_id: str | None = None
    evidence: str | None = None
    source_command: str | None = None


class IntentDatasetBridge:
    """Immutable search index over the external, proposed utterance set."""

    def __init__(self, root=DATA_ROOT):
        root = Path(root)
        catalog = CATALOG if root.resolve() == DATA_ROOT.resolve() else type(CATALOG)(root.parent)
        payloads = {name: json.loads((root / name).read_text()) for name in (
            "command-sequences.json", "segmentation-examples.json")}
        outcomes = list(catalog.intents.values())
        utterances = [example for row in outcomes for example in row['examples']]
        sequences = payloads["command-sequences.json"]["sequences"]
        self.catalog_revision = catalog.revision
        self.outcomes = {item["id"]: item for item in outcomes}
        self.phrases: dict[str, list[DatasetPhrase]] = {}
        by_variant = {}
        for row in utterances:
            if row["intent"] not in self.outcomes:
                raise ValueError(f"Unknown dataset intent: {row['intent']}")
            phrase = DatasetPhrase(row["intent"], row["variant"], row["text"],
                                   row["origin"], row["arguments"])
            self.phrases.setdefault(normalize(row["text"]), []).append(phrase)
            by_variant[(row["intent"], row["variant"])] = phrase
        if len(by_variant) != len(utterances):
            raise ValueError("Duplicate dataset variant")
        self.variants = by_variant
        self.sequences = {}
        for row in sequences:
            for step in row["steps"]:
                if (step["intent"], step["variant"]) not in by_variant:
                    raise ValueError(f"Unknown sequence step: {row['id']}")
            self.sequences.setdefault(normalize(row["utterance"]), []).append(row)
        self.segmentation_examples = {}
        for row in payloads["segmentation-examples.json"]["examples"]:
            self.segmentation_examples[normalize(row["utterance"])] = row

    @staticmethod
    def split_clauses(text):
        """Return literal clauses; `and` between target nouns stays intact."""
        return tuple(part.strip() for part in _BOUNDARY.split(text) if part.strip())

    def preview(self, text):
        """Classify exact dataset wording, then expose unlabeled clause splits."""
        key = normalize(text)
        if not key:
            return DatasetPreview(text, "unrecognized")
        sequences = self.sequences.get(key, ())
        if len(sequences) == 1:
            row = sequences[0]
            return DatasetPreview(text, "sequence", self.split_clauses(text),
                                  intent_ids=tuple(step["intent"] for step in row["steps"]),
                                  sequence_id=row["id"], evidence=row["evidence"],
                                  source_command=row["source_command"])
        if len(sequences) > 1:
            return DatasetPreview(text, "ambiguous", self.split_clauses(text),
                                  evidence="multiple_sequence_examples")
        example = self.segmentation_examples.get(key)
        if example:
            return DatasetPreview(text, "sequence" if len(example["segments"]) > 1 else "single",
                                  self.split_clauses(text),
                                  intent_ids=tuple(step["intent"] for step in example["segments"]),
                                  evidence=example["evidence"], source_command=example["source_command"])
        phrases = tuple(self.phrases.get(key, ()))
        ids = tuple(sorted({phrase.intent for phrase in phrases}))
        if phrases:
            return DatasetPreview(text, "single" if len(ids) == 1 else "ambiguous",
                                  (text,), phrases, ids, evidence="illustrative_utterance")
        clauses = self.split_clauses(text)
        return DatasetPreview(text, "unlabeled_sequence" if len(clauses) > 1 else "unrecognized",
                              clauses if len(clauses) > 1 else ())
