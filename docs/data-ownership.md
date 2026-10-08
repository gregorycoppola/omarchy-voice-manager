# Shared data and personal overrides

## Ownership

- The `bundled/intents` directory in this repository owns intent schemas, examples, provider
  grammar/vocabulary/bindings, browser spelling forms, rule priority, and window-name forms.
- Skipper owns parsing algorithms, desktop discovery, executable handlers,
  safety/confirmation rules, UI, and persistence. A dataset addition cannot invent
  an executor. Skipper's workspace-switch adapter activates the shared catalog's
  `workspace.switch` template for the existing 1–10 workspace vocabulary until
  the provider definition supplies that binding. Dynamic window names and identities
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
Recordings and diagnostic logs remain local files outside the shared intent data.
The experimental debugger has the separate storage and cloud behavior below.

## Command runtime lookup precedence

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
counts of resolved typed commands are exposed for inspection, but ranking uses
text matching and catalog order, not frequency.
Selecting a suggestion submits its text to the same parser; it never replays a saved target.

## Experimental debugger storage and cloud requests

Local voice input and the parser debugger share a history database separate from the command runtime:
Normal voice mode executes supported commands and shows feedback in the top dropdown.
The explicitly enabled debugger only previews commands.

- Observations, reviews, and model-call history: `~/.local/state/skipper/history.sqlite3`.
- Audio: `~/.local/state/skipper/recordings/`.
- Confirmed phrase rules: `~/.local/share/skipper/grammar/current.json`.

These respect `XDG_STATE_HOME` and `XDG_DATA_HOME`. Inputs, captured desktop
context, requests, and responses may contain personal information; keep them out
of Git and shared reports.

The debugger tries its speech grammar and confirmed phrase mappings locally.
With **Use OpenAI** enabled and credentials available, unmatched nonempty text
and grammar vocabulary/context are sent for interpretation and possible rule
proposals. The checkbox starts disabled. Audio is not sent by this fallback.
Review and activation of a phrase mapping are separate from interpretation;
the debugger never executes the resulting desktop command.

## Installation

The Omarchy manifest and setup command are in this application repository.
`python plugin_setup.py install --shortcut --autostart` validates the bundled
intent dataset, prepares the Python environment, initializes local SQLite, and
installs launchers plus the optional Super+R shortcut and login integration.
The basic install downloads no speech model or second repository. `--voice` installs
speech dependencies; `--download-model` explicitly downloads the pinned model.
Model configuration and optional OpenAI credentials are stored under
`~/.config/skipper` (or `XDG_CONFIG_HOME`).

The runtime uses `bundled/intents` inside its own checkout. Updating the plugin
updates the bundle with it; restart Skipper to load the new version. Old copies
under `~/.local/share/skipper/intent-dataset` are preserved but no longer selected.
Sibling checkouts are never selected implicitly.

Developers can set `OMARCHY_INTENT_DATASET=/absolute/path` explicitly for setup
and runtime. This trusted override loads both catalog data and Python reader code
from that path. The former `--dataset` setup flag is replaced by this environment
variable; normal users need neither.

Intent definitions and application changes are reviewed and committed together.
The catalog loader computes a revision from the definition contents; no upstream
repository or commit pin is required. Personal data is never included in that bundle.

Normal voice mode also supports an explicitly enabled `voice_cloud` setting.
It sends unmatched nonempty transcripts and grammar/desktop vocabulary to OpenAI,
with the same local audit storage as the debugger. Audio stays local. Validated
literal interpretations can execute through the normal runtime; suspected
mishearings need clarification. Enabling this does not automatically save rules.
