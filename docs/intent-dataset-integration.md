# Built-in intent catalog

Skipper owns its intent definitions and catalog loader in `bundled/intents`.
`dataset-reference.json` selects that local directory and provider `skipper`.
The definitions ship and evolve with the application; there is no upstream
repository requirement, download, or synchronization step.

`OMARCHY_INTENT_DATASET=/absolute/path` explicitly overrides the bundle for
trusted development. No sibling checkout or old installed snapshot is selected
automatically. See [installation and data ownership](data-ownership.md).

The dataset owns all shared schemas, examples, static Skipper grammar patterns,
fixed vocabulary, dynamic vocabulary declarations, and mappings to executor
arguments. `command_catalog.py` constructs compatibility views from that data.
The app currently activates the shared `workspace.switch` schema's direct
templates for workspaces 1–10 through a local executor adapter; the current
provider definition does not yet contain that binding.
The runtime bundle contains the catalog, Skipper provider, sequence examples,
catalog reader, and license. Research archives and Git history are excluded.
`python import_intent_dataset.py` now validates the reference and reports the
loaded revision without copying files.

Edit `bundled/intents/data/catalog.json` for contracts and examples, or
`bundled/intents/data/providers/skipper.json` for wording and executor bindings.
Run `python -B import_intent_dataset.py` from the application root to validate
the catalog and compile the phrases, then run the relevant parser tests.
Commit definition changes together with their app changes and restart Skipper
and its native Explorer. Catalog revisions are content hashes of the catalog
and provider files, so definition edits automatically change the revision.
A missing or invalid catalog prevents startup with an explanatory error.

Every compiled rule binds its slots, translates its existing executor arguments
into canonical intent instances, and validates those against the shared schema.
Window identities come from the current request context; installed app names
are discovered locally. Skipper retains execution handlers, target checks,
confirmation, fuzzy thresholds, and saved correction compatibility.

```python
from intent_matching import IntentMatcher

matcher = IntentMatcher('/tmp/example-aliases.json')
parsed = matcher.parse('open the browser')
assert parsed.canonical_plan == [{
    'intent': 'browser.open',
    'arguments': {'browser': 'default', 'presentation': 'fullscreen'},
}]
assert matcher.parse_instance(parsed.canonical_plan[0]).command == parsed.command
```

`parse_instance` is the entry point for future LLM output. It accepts only
schema-valid objects with an existing matching executor binding. It does not run
actions. The catalog currently validates 227 intent schemas, but a schema alone does not
activate an action in Skipper. The typed runtime supports queued ordinary
commands through Add step; some interactive providers require a separate action.
The catalog reader can validate structured plans, but that does not make arbitrary
external-provider plans executable.

The native Explorer shows shared contracts and canonical parser output.
Diagnostics include `catalog_revision` and `canonical_plan`, alongside the old
executor intent required by existing corrections and runtime code.

The catalog loader in `bundled/intents/intent_explorer/catalog.py` provides
instance and plan validation, grammar bindings, and LLM schema/context export.
See [the catalog guide](../bundled/intents/README.md) for the file layout.
