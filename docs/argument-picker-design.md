# Prefix groups, arguments, and command sequences

The picker groups commands by verb and then by arguments. A unique matching
branch can expand while typing; a completed action requires Enter. Focus goes
to a window; Show brings it to the current workspace.

## Interaction

- Empty input shows verb groups derived from the first word of supported command
  wording: open, minimize, maximize, move, close, list, tile, and others.
  Empty input uses a fixed common-verb order followed by alphabetical order.
- Typing filters groups. At the verb level use case-insensitive substring matching;
  an exact verb wins, otherwise several matching verbs remain visible.
- A single matching branch reveals its children automatically. Keep the input
  editable; deleting/changing it recomputes inferred levels. The accepted or
  inferred prefix stays visible above the input.
- Several matches pause expansion. Tab accepts the highlighted choice, defaulting
  to the top one. Up/Down changes the highlighted choice. Enter on a branch also
  continues; Enter on a completed action executes.
- A single final action stays visible. It is never executed automatically.
- Tab on a final command fills its complete wording. Tab on a website fills its
  URL. Enter executes. This supersedes the earlier website-only Tab-to-open rule.
- Shift+Tab or Back returns to the previous level. Backspace on empty input also
  goes back. Returning deliberately suppresses automatic re-expansion until the
  input changes or the user explicitly accepts a choice. Escape cancels.

Example: `open web` reveals **website in new browser…** and **website in
existing browser…** as complete choices. `show` reveals **all windows**,
**the terminals**, **Chrome**, etc., not separate **the…** or **all…** groups. If several branches match, Tab accepts the top/highlighted
one; typing `ex` narrows to existing browser and reveals its arguments.

## Two kinds of expansion

1. **Verb prefixes** group existing command wording. After the verb, retain the
   whole meaningful command chunk; do not mechanically create a level per word. The first word is treated
   as the verb by catalog convention. The verb is an intent family, not a complete
   logical intent. Later words distinguish its operations and arguments.
2. **Argument providers** supply workspace numbers, browser windows, or websites.
   Reaching one requests or constructs its available choices.

Both appear as levels in the picker. Prefix expansion never causes execution.
Keep visible aliases: `minimize this window` appears under **minimize**, even if
its logical action is shared with `hide this window`. Multiword phrases such as
`bring up` group under **bring** and retain the rest of their wording.

## Implementation and matching

`config/skipper-bar/CommandLevels.js` builds the verb roots from the supported
catalog and dynamic suggestions. Each prefix node holds a lazy child provider;
children are materialized and cached when that path is reached. Below a verb,
levels come from explicit command/argument structure, not shared filler words. Named-window workspace rows are also built lazily,
avoiding the former eager window × workspace expansion.

The underlying supported catalog and dynamic phrases are still supplied by the
runtime; this does not yet make every backend vocabulary generator lazy. The QML
picker reuses its tree across status updates when those source lists are unchanged.

`preview()` computes inferred paths and leftover input without committing the
text. Tab commits the selected path. Back restores a prior input/selection.
Substring verb matching gates the root; remaining choices use the existing cheap
ordered-subsequence filter and bounded text reranking. Frequency does not pick a
command prefix. Uniqueness is assessed before the ten-row display limit.

## Window movement

Move first offers the current window and individual named windows in one list.
Selecting a window reveals a combined list of workspace and monitor destinations.

Workspace choices currently cover 1–10, with typed positive move destinations
of up to nine digits. Switching workspaces retains the catalog's supported range.
Named workspace commands require an exact, unique name in captured window
vocabulary. The executor rechecks target identity and rejects closed, replaced,
missing, or ambiguous targets rather than substituting another window.

## Website levels and history

Under **open**, offer **website in new browser…** and **website in existing
browser…** as complete chunks. Reaching either loads the website argument. Existing browser selects
the captured focused Chrome/Chromium window or the sole supported window; multiple
possible windows add a browser-choice level. Shift+Tab returns through those
levels. If no supported window exists, explain that rather than silently opening
another browser. A draft URL survives the browser-choice level.

`site_history.SiteHistory` reads local browser history asynchronously, sums page
visit counts by hostname, and returns origins ranked by visits, then last visit,
then hostname. It caches results in memory for 60 seconds. Show ten choices and
allow a new URL. Bookmarks and Skipper command counts do not seed this list.
A locked database is read via a disposable private snapshot; report unavailable
sources. Browser files are never modified.

Existing-window execution requires the configured Playwright extension connection.
The adapter checks native identity and extension focus, then creates a new tab in
that specific Chrome/Chromium window. New-browser execution uses the configured
browser launcher with --new-window. Preserve existing tabs and window layout.

## Sequences and execution

A command is an intent with arguments; a sequence is an ordered list of complete
commands. **Add step** queues a completed ordinary command. Tab never queues or
executes. Website flows cannot currently join a sequence; run queued commands
before entering a website flow. Execution retains existing confirmation and
window-identity checks.

## Optional app arguments

App rows are provided by installed desktop entries with available executable
launchers. The picker uses their literal names, not generic browser aliases.
An app row is an executable branch: Enter opens it in the captured workspace;
Tab opens a destination level with “in this workspace” first and workspaces 1–10
following. Each destination is also executable. Tab continues to the layout
choices: retain the app’s layout or tile it with the destination’s other windows.
Shift+Tab returns through these levels. No argument selection launches an app.
Add step accepts these executable branches with their current defaults.

The runtime parses optional clauses exactly against the current installed-app
vocabulary. It records `launch_options` beside the base intent and canonical
plan; these options are execution parameters, not part of that base plan.
A launch is followed by identification of a new window and the existing
identity-checked workspace movement. Existing windows are never substituted when
an app declines to create another window. Layout exclusions still apply.

## Category order and named pairs

Browsing Tile or List keeps all windows, all terminals, and all browsers first.
Tile also offers two specific windows and monitor choices; the all-apps category
is omitted from the picker. Filtering
by a window/category name still uses the usual text ranking.

The two-specific-windows provider exposes captured, uniquely labeled windows.
Tab chooses the first, then the second; the first is omitted from the second
list. Names with identical titles receive distinguishing identity suffixes.
Enter on the final choice runs `tile <first name> and <second name>`. Back returns
through both selections. The lazy tree avoids eagerly constructing every pair.

The parsed pair stores two window IDs and uses the existing tiling executor,
which verifies identities and rejects stale or replaced windows. It gathers the
two windows on the captured workspace and temporarily hides the other windows
there. The picker describes this behavior before execution.

## Workspace-scoped tiling

Tile categories for windows, terminals, and browsers are executable branches.
Enter uses the current default; Tab exposes “this workspace” and numbered
workspace destinations. Explicit workspace requests affect that workspace's
matching windows. The parser also accepts positive workspace numbers beyond
the numbered menu options.
