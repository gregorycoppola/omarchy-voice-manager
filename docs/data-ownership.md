# Shared data and personal overrides

## Ownership

- The independent intent dataset owns shared intent schemas, examples, provider
  grammar/vocabulary/bindings, browser spelling forms, rule priority, and window-name forms.
- Skipper owns parsing algorithms, desktop discovery, executable handlers,
  safety/confirmation rules, UI, and persistence. A dataset addition cannot invent
  an executor. Skipper's workspace-switch adapter activates the shared catalog's
  `workspace.switch` template for the existing 1–10 workspace vocabulary until
  the provider snapshot supplies that binding. Dynamic window names and identities
  come from the current desktop.
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

The written-command dropdown searches supported intent phrases and current dynamic
commands. Saved command wording remains in SQLite and never becomes a menu source;
counts of resolved typed commands rank supported suggestions by frequency.
Selecting a suggestion submits its text to the same parser; it never replays a saved target.

## Installation

The Omarchy manifest and setup command are in this application repository.
`python plugin_setup.py install --shortcut --autostart` validates the bundled
intent dataset, prepares the Python environment, initializes local SQLite, and
installs launchers plus the optional Super+R shortcut and login integration.
No speech model or second GitHub repository is downloaded.

The runtime uses `bundled/intents` inside its own checkout. Updating the plugin
updates the bundle with it; restart Skipper to load the new version. Old copies
under `~/.local/share/skipper/intent-dataset` are preserved but no longer selected.
Sibling checkouts are never selected implicitly.

Developers can set `OMARCHY_INTENT_DATASET=/absolute/path` explicitly for setup
and runtime. This trusted override loads both catalog data and Python reader code
from that path. The former `--dataset` setup flag is replaced by this environment
variable; normal users need neither.

Shared source is maintained separately, while every application release ships a
compatible licensed snapshot. Personal data is never included in that bundle.
