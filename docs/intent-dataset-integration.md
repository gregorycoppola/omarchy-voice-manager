# External intent dataset

Skipper now loads the independent `omarchy-voice-dataset` repository directly.
`dataset-reference.json` selects provider `skipper` and pins a public dataset
commit. Setup downloads that snapshot automatically. Development can use a
sibling checkout; `OMARCHY_INTENT_DATASET=/absolute/path` overrides its location.
See [installation and data ownership](data-ownership.md) for lookup order.

The dataset owns all shared schemas, examples, static Skipper grammar patterns,
fixed vocabulary, dynamic vocabulary declarations, and mappings to executor
arguments. `command_catalog.py` constructs compatibility views from that data.
There is no application copy of `data/intent_dataset` and no manual phrase import.
`python import_intent_dataset.py` now validates the reference and reports the
loaded revision without copying files.

Edit `data/catalog.json` for shared contracts and examples, or
`data/providers/skipper.json` for active Skipper wording and bindings. Restart
Skipper and its native Explorer after changes. The browser explorer reads the
catalog directly on refresh. A missing or invalid dataset prevents startup with
an explanatory error, rather than silently loading stale embedded definitions.

Every compiled rule binds its slots, translates its existing executor arguments
into canonical intent instances, and validates those against the shared schema.
Window IDs are still captured at recording start; installed app names are still
discovered locally. Skipper retains execution handlers, target checks,
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
actions. Schema support for all 223 research intents does not activate all of them
in Skipper. Multi-step source macros retain their existing executor; general
sequence execution and external provider adapters remain future work.

The native Explorer shows shared contracts and canonical parser output.
Diagnostics include `catalog_revision` and `canonical_plan`, alongside the old
executor intent required by existing corrections and runtime code.

The dataset's `docs/structured-intents.md` documents schemas, references, Python
iteration, grammar templates, LLM export, historical audit preservation, and
editing workflow. The [public dataset](https://github.com/gregorycoppola/omarchy-voice-dataset)
is versioned independently; each app release pins a compatible public commit.
Runtime reads the local installed snapshot without accessing GitHub per command.
