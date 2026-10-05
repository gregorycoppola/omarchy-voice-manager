# External intent dataset

Skipper ships a runtime snapshot in `bundled/intents`. `dataset-reference.json`
selects provider `skipper` and records the upstream repository and source commit
for attribution and repeatable updates. That reference is provenance, not an
installation download: only the Skipper repository is needed.

`OMARCHY_INTENT_DATASET=/absolute/path` explicitly overrides the bundle for
trusted development. No sibling checkout or old installed snapshot is selected
automatically. See [installation and data ownership](data-ownership.md).

The dataset owns all shared schemas, examples, static Skipper grammar patterns,
fixed vocabulary, dynamic vocabulary declarations, and mappings to executor
arguments. `command_catalog.py` constructs compatibility views from that data.
The app currently activates the shared `workspace.switch` schema's direct
templates for workspaces 1–10 through a local executor adapter; the pinned
provider snapshot does not yet contain that binding.
The runtime bundle contains the catalog, Skipper provider, sequence examples,
catalog reader, and license. Research archives and Git history are excluded.
`python import_intent_dataset.py` now validates the reference and reports the
loaded revision without copying files.

In the upstream dataset repository, edit `data/catalog.json` for shared contracts and examples, or
`data/providers/skipper.json` for active Skipper wording and bindings. Refresh the application bundle from the selected committed snapshot, then restart
Skipper and its native Explorer. The browser explorer reads the
catalog directly on refresh. A missing or invalid dataset prevents startup with
an explanatory error, rather than falling back to a different dataset.

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
is versioned independently; each app release bundles a compatible snapshot.
Neither setup nor runtime needs to fetch that repository.
