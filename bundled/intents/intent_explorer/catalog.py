"""Shared intent contracts, provider bindings and LLM schema export (stdlib only)."""
import copy
import hashlib
import json
from pathlib import Path


def validate(value, schema, path="arguments"):
    """Validate the JSON Schema subset authored by this catalog.

    This is deliberately a small validator, not a general JSON Schema engine.
    The exported schemas use standard JSON Schema 2020-12 keywords.
    """
    for union in ("oneOf", "anyOf"):
        if union in schema:
            matches = 0
            for option in schema[union]:
                try:
                    validate(value, option, path)
                    matches += 1
                except ValueError:
                    pass
            if not matches or (union == "oneOf" and matches != 1):
                raise ValueError(f"{path}: does not match {union}")
    if "const" in schema and (type(value) is not type(schema["const"]) or value != schema["const"]):
        raise ValueError(f"{path}: expected {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: expected one of {schema['enum']}")
    kind = schema.get("type")
    valid = {"object": isinstance(value, dict), "array": isinstance(value, list),
             "string": isinstance(value, str), "integer": type(value) is int,
             "number": type(value) in (int, float), "boolean": type(value) is bool,
             "null": value is None}
    if kind and (kind not in valid or not valid[kind]):
        raise ValueError(f"{path}: expected {kind}")
    if kind == "object":
        props = schema.get("properties", {})
        missing = set(schema.get("required", ())) - value.keys()
        unknown = value.keys() - props.keys()
        if missing or (unknown and schema.get("additionalProperties") is False):
            raise ValueError(f"{path}: missing {sorted(missing)}, unknown {sorted(unknown)}")
        for key in value.keys() & props.keys():
            validate(value[key], props[key], f"{path}.{key}")
    if kind == "array":
        if len(value) < schema.get("minItems", 0):
            raise ValueError(f"{path}: too few items")
        for index, item in enumerate(value):
            validate(item, schema["items"], f"{path}[{index}]")
    if kind == "string" and len(value) < schema.get("minLength", 0):
        raise ValueError(f"{path}: empty string")
    if kind in ("number", "integer"):
        import math
        if not math.isfinite(value) or value < schema.get("minimum", -float("inf")) or value > schema.get("maximum", float("inf")):
            raise ValueError(f"{path}: value outside permitted range")


def bind(template, arguments):
    """Bind $argument leaves while preserving structured objects and literals."""
    if isinstance(template, str) and template.startswith("$"):
        if template[1:] not in arguments:
            raise ValueError(f"Unbound argument {template}")
        return copy.deepcopy(arguments[template[1:]])
    if isinstance(template, dict):
        return {key: bind(value, arguments) for key, value in template.items()}
    if isinstance(template, list):
        return [bind(value, arguments) for value in template]
    return template


class Catalog:
    def __init__(self, root=None):
        self.root = Path(root) if root else Path(__file__).resolve().parents[1]
        content = (self.root / "data/catalog.json").read_bytes()
        self.data = json.loads(content)
        if self.data.get("schema_version") != 2:
            raise ValueError("Expected intent dataset schema version 2")
        self.intents = {row["id"]: row for row in self.data["intents"]}
        if len(self.intents) != len(self.data["intents"]):
            raise ValueError("Duplicate intent IDs")
        self.providers = {}
        digest = hashlib.sha256(content)
        for path in sorted((self.root / "data/providers").glob("*.json")):
            data = path.read_bytes()
            provider = json.loads(data)
            if provider.get("schema_version") != 2 or provider.get("provider") != path.stem:
                raise ValueError(f"Invalid provider: {path}")
            self.providers[path.stem] = provider
            digest.update(path.name.encode() + b"\0" + data)
        self.revision = digest.hexdigest()[:16]
        for row in self.intents.values():
            if len(row["examples"]) != 10 or {e["variant"] for e in row["examples"]} != set(range(1, 11)):
                raise ValueError(f"Expected ten variants: {row['id']}")
            for example in row["examples"]:
                self.validate_instance({"intent": example["intent"], "arguments": example["arguments"]})
                if example["intent"] != row["id"]:
                    raise ValueError("Example belongs to another intent")
            for rule in row['grammar']:
                example = next(e for e in row['examples'] if e['variant'] == rule['example_variant'])
                arguments = bind(rule['arguments'], {name: slot['example_value'] for name, slot in rule['slots'].items()})
                phrase = rule['pattern']
                for name, slot in rule['slots'].items():
                    phrase = phrase.replace('<' + name + '>', slot['example_text'])
                if arguments != example['arguments'] or phrase != example['text']:
                    raise ValueError(f"Template differs from example: {rule['id']}")

    def validate_instance(self, instance):
        if not isinstance(instance, dict) or set(instance) != {"intent", "arguments"}:
            raise ValueError("An intent instance requires exactly intent and arguments")
        if not isinstance(instance['intent'], str):
            raise ValueError('Intent name must be a string')
        definition = self.intents.get(instance["intent"])
        if definition is None:
            raise ValueError(f"Unknown intent: {instance['intent']}")
        validate(instance["arguments"], definition["arguments_schema"])
        return instance

    def canonical_plan(self, provider, executor_type, arguments):
        adapter = self.providers[provider]
        if executor_type == "desktop_action":
            template = adapter["desktop_bindings"].get(arguments.get("action"))
        else:
            template = adapter["canonical_bindings"].get(executor_type)
        for case in adapter.get('canonical_cases', {}).get(executor_type, []):
            if all(arguments.get(key) == value for key, value in case['when'].items()):
                template = case['steps']
                break
        if template is None:
            raise ValueError(f"No {provider} binding for {executor_type}")
        steps = bind(template, arguments)
        return self.validate_plan(steps)

    def validate_plan(self, steps):
        if not isinstance(steps, list) or not steps:
            raise ValueError('An intent plan must be a nonempty list')
        prior = set()
        def references(value):
            if isinstance(value, dict):
                if value.get("kind") == "result" and value["value"].split(".")[0] not in prior:
                    raise ValueError("Result reference must name an earlier step")
                for item in value.values():
                    references(item)
            elif isinstance(value, list):
                for item in value:
                    references(item)
        for step in steps:
            self.validate_instance({k: v for k, v in step.items() if k != "id"})
            references(step["arguments"])
            if "id" in step:
                if step["id"] in prior:
                    raise ValueError("Duplicate step ID")
                prior.add(step["id"])
        return steps

    def llm_schema(self, intent_ids=None):
        """Schema for one canonical intent; select IDs for a provider's capabilities."""
        ids = sorted(self.intents if intent_ids is None else intent_ids)
        if not ids:
            raise ValueError("Choose at least one intent")
        return {"$schema": "https://json-schema.org/draft/2020-12/schema",
                "title": "Omarchy intent instance", "oneOf": [
                    {"type": "object", "properties": {
                        "intent": {"const": name},
                        "arguments": copy.deepcopy(self.intents[name]["arguments_schema"])},
                     "required": ["intent", "arguments"], "additionalProperties": False}
                    for name in ids]}

    def llm_context(self, intent_ids=None, context=None):
        ids = sorted(self.intents if intent_ids is None else intent_ids)
        return {"catalog_revision": self.revision, "instructions":
                "Return an intent name and arguments matching the schema. Resolve IDs only "
                "from supplied context. Preserve unresolved names/context references. "
                "Missing information needs clarification before execution. Schema validity "
                "does not imply that an executor supports this argument combination.",
                "intents": [{"intent": name, "description": self.intents[name]["description"],
                             "arguments_schema": self.intents[name]["arguments_schema"],
                             "grammar": self.intents[name]['grammar'],
                             "examples": [{"text": e['text'], "intent": name, "arguments": e['arguments']}
                                          for e in self.intents[name]['examples'][:2]]} for name in ids],
                "context": context or {}, "output_schema": self.llm_schema(ids)}
