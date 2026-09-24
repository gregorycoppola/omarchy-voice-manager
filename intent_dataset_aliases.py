"""Small, explicit promotion list from dataset examples to existing commands."""

import json
from pathlib import Path

from command_catalog import EXACT_ONLY_COMMANDS, GRAMMAR, STRUCTURED_INTENTS
from grammar_engine import normalize
from intent_dataset_bridge import DATA_ROOT, IntentDatasetBridge
from dataset_source import PROVIDER

APPROVED_PATH = DATA_ROOT / "providers" / "skipper.json"


def load_approved_aliases(path=APPROVED_PATH, bridge=None):
    """Return exact phrase→command mappings after validating the bundle and IDs."""
    bridge = bridge or IntentDatasetBridge()
    data = json.loads(Path(path).read_text())
    if data.get("schema_version") != 2 or not isinstance(data.get("approved_aliases"), list):
        raise ValueError("Invalid approved dataset alias file")
    aliases = {}
    for row in data["approved_aliases"]:
        intent_id, variant, command = row["intent"], row["variant"], row["command"]
        if command not in STRUCTURED_INTENTS or command not in EXACT_ONLY_COMMANDS:
            raise ValueError(f"Dataset alias target is not an exact Skipper command: {command}")
        source_text = bridge.variants[(intent_id, variant)].text
        expected = {"intent": intent_id, "arguments": bridge.variants[(intent_id, variant)].arguments}
        if STRUCTURED_INTENTS[command].canonical_plan() != [expected]:
            raise ValueError(f"Dataset alias arguments disagree with executor: {intent_id}:{variant}")
        if row.get("text") != source_text:
            raise ValueError(f"Reviewed dataset wording changed: {intent_id}:{variant}")
        phrase = normalize(source_text)
        if not phrase or (phrase in GRAMMAR and GRAMMAR[phrase] != command):
            raise ValueError(f"Dataset alias conflicts with built-in grammar: {phrase}")
        if phrase in aliases and aliases[phrase] != command:
            raise ValueError(f"Dataset alias has two commands: {phrase}")
        if phrase not in GRAMMAR:
            aliases[phrase] = command
    return aliases
