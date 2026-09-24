# Shared data and personal overrides

## Ownership

- The independent intent dataset owns shared intent schemas, examples, provider
  grammar/vocabulary/bindings, browser spelling forms, rule priority, and window-name forms.
- Skipper owns parsing algorithms, desktop discovery, executable handlers,
  safety/confirmation rules, UI, and persistence. A dataset addition cannot invent
  an executor. Dynamic window names and identities come from the current desktop.
- Personal aliases, corrections (including their audit trail), named shortcuts,
  preferences, and command history live in SQLite outside every Git checkout.

Default database: `~/.local/state/skipper/command-history.sqlite3`, respecting
`XDG_STATE_HOME`. Directory mode is 0700; database mode is 0600. Treat it as PII.
The `commands` table preserves history. The `personal` table contains validated,
versioned JSON documents for aliases, corrections, shortcuts, and settings. These
are SQLite rows, not new JSON files. Saved actions/aliases include canonical plans
as well as compatibility executor IDs; wording corrections re-resolve live targets.

On first use, legacy files from `~/.local/share/skipper/` (`XDG_DATA_HOME`) are
imported per namespace in a transaction. Originals remain untouched except for
owner-only permissions and serve as backups. Once imported, SQLite is authoritative;
editing old JSON files has no effect. Malformed legacy data fails visibly rather
than silently resetting preferences. New users get an empty database automatically.
Recordings and diagnostic logs remain separate private local files; they are not
shared intent data and are not uploaded.

## Lookup precedence

1. Explicit personal speech corrections, only for speech. Typed requests bypass
   speech corrections. Corrected wording is reparsed once, without correction
   chaining or a new fuzzy guess.
2. Dataset-scoped spelling normalization, then dataset-declared specific exact
   rules before general free-text frames (such as a two-window tiling request).
3. Exact shared grammar, reviewed dataset aliases, personal aliases/shortcuts,
   and live vocabulary. Shared wording is reserved when creating personal aliases
   or shortcuts. Competing meanings from dynamic targets are ambiguous, not silently
   overridden. Explicit speech correction is the intentional override mechanism.
4. Confidence-filtered fuzzy parsing. Named shortcuts and installed-app names are
   exact-only; destructive/sensitive command guards and confirmations still apply.

The history dropdown has its own fuzzy *search*: it suggests previous wording,
then submits the selected text to this same parser. It never replays a saved target.

## Installation

The Omarchy manifest and setup command are in this application repository.
`python plugin_setup.py install --shortcut --autostart` fetches the public dataset
commit pinned in `dataset-reference.json`, validates it, installs it under
`~/.local/share/skipper/intent-dataset`, prepares the Python environment and speech
model, and installs both Super+R and Super+Shift+R shortcuts. SQLite is initialized
for the installing user; no developer history is distributed.

`--dataset /path/to/checkout` selects an explicit dataset instead. `--text-only`
skips the speech-model download; launch with `SKIPPER_TEXT_ONLY=1` for keyboard mode.
The runtime resolves an explicit `OMARCHY_INTENT_DATASET` first, the development
sibling checkout second, and the installed snapshot third. Normal command handling
never fetches GitHub. Dataset upgrades happen during explicit setup, preserve one
previous snapshot, and require a runtime restart.

The dataset is public. Application development still stays private; publishing
an updated application plugin remains a separate public snapshot release.
