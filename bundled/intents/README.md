# Skipper intent definitions

This directory is the authoritative source for Skipper's intent definitions and
catalog loader. Edit and commit these files together with the application code.
Installation and runtime read them locally without fetching another repository.

- `data/catalog.json`: intent schemas, grammar templates, and examples.
- `data/providers/skipper.json`: Skipper vocabulary, rules, and executor bindings.
- `data/command-sequences.json` and `data/segmentation-examples.json`: sequence examples.
- `intent_explorer/catalog.py`: catalog loading, validation, and schema export.

From the application root, run `python -B import_intent_dataset.py` to validate
the catalog and compile Skipper's phrases. Restart Skipper after editing definitions.
Catalog revisions are content hashes computed from schemas and provider files.

These files originated in the Omarchy Voice Dataset and retain GPL-3.0-only
licensing; see LICENSE. They are now maintained as part of Skipper.
Personal history, recordings, aliases, and settings belong in per-user storage.
