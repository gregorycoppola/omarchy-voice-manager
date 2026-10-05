# Skipper

Skipper is a desktop command app for Linux / Omarchy. The current interface is
**text and dropdown menus first**. Voice remains a product goal, with recognition
planned through an external provider such as Voxtype.

## How it works now

1. Press **Super + R** to see verb groups. Type to narrow the shared prefixes; a unique matching branch expands automatically.
2. With multiple choices, **Tab** accepts the highlighted option (the top one by default). **Shift + Tab** goes back. Final actions never run automatically.
3. Press **Enter** to run a complete command. For an installed app, Enter opens a new window in this workspace; **Tab** continues through optional workspace and tiling choices. You can run after any choice. Use **Add step** to queue a sequence.
4. Skipper resolves the intended action and window, applies confirmations, and
   records the result in local command history.

The picker uses an ordered subsequence filter, then a deeper text score on a
shortlist. Frequency does not influence ranking yet. See the
[matching notes](docs/command-matching-notes.md) and
[argument picker design](docs/argument-picker-design.md).

**Tile** and **List** begin with **all windows**, **all terminals**, then
**all browsers**. **Tile → two specific windows…** lets you choose the first
window by name, then a different second window. Enter runs the completed pair:
both windows are tiled on the captured workspace and the other windows there
are temporarily hidden. The first window does not have to be the focused one.

Skipper no longer contains a microphone recorder, speech model loader, or custom
transcription engine. A future voice adapter will feed text into the same command
and argument system. See the [Voxtype plan](docs/voxtype-integration-plan.md).
Existing recordings, transcripts, corrections, and model files are preserved;
History can still play saved audio. Retranscription is not currently available.

## About this checkout

Copyright (C) 2026 Greg Coppola. Skipper's original code is licensed under
**GNU GPL version 3 only** (`GPL-3.0-only`). You may redistribute and modify it
under those terms. It is provided without warranty, including any implied
warranty of merchantability or fitness for a particular purpose. See [LICENSE](LICENSE)
and [third-party notices](THIRD_PARTY_NOTICES.md).

Current release: **0.3.1**. See [the changelog](CHANGELOG.md).

Skipper's windowless background process handles commands and actions. The menu
bar provides its dropdown interface. **Skipper Explorer** is the separate native
app for command inspection, saved history, learned phrases, and settings.

## Install as an Omarchy plugin

Requires Omarchy Quattro with the Lua Hyprland API and Quickshell. Tested on
Linux aarch64; x86_64 has not yet been tested. No speech backend is enabled in this development version.

```bash
omarchy plugin add https://github.com/gregorycoppola/omarchy-voice-manager.git --enable
python ~/.config/omarchy/plugins/greg.skipper/plugin_setup.py install --shortcut --autostart
```

Run setup yourself in a terminal: Omarchy does not run installation hooks.
Setup creates a Python environment under `${XDG_DATA_HOME:-~/.local/share}/skipper`,
outside the plugin checkout. It needs system `python`, `gtk4`, `python-gobject`,
`python-cairo`, `hyprctl`, and `gapplication` (GLib). File search uses `fd`
and `xdg-open`; audio defaults use `pactl`; system controls use `nmcli`, BlueZ,
and Hyprsunset when available. It does not download speech
models or install inference dependencies. The shared command dataset is bundled
with the plugin; setup needs no second GitHub repository.
Install missing system packages through Omarchy's package manager first.
The widget has a **Start Skipper** button; setup does not start recording.

`--shortcut` assigns **Super+R** to the command picker. Omit it if you
want to configure a different binding yourself using
`config/hyprland-skipper-written.lua`. `--autostart` adds a login launcher; omit it
for manual startup. Existing conflicting Skipper files are refused unless you
supply `--replace-existing`, which backs them up first. Setup preserves other
bindings and stores a receipt so uninstall only removes its own integration.

App-opening choices come from visible installed desktop entries with available
launchers, using literal names such as **Chromium**, **Brave**, or **Foot**.
An app missing from the current scan is not offered. **Open terminal** remains an
alias for the installed configured terminal, alongside its literal app name. Tab after an app shows
**in this workspace** first, then workspaces 1–10; Tab after a destination offers
its normal layout or **tile with the other windows**. Enter runs at either stage.
For example: `open Chromium in workspace 3 and tile`. Typed commands also accept
positive workspace numbers up to nine digits.

New windows are raised to the front and focused after placement or tiling.
“This workspace” means the workspace captured when the picker opened. Skipper
requests a new window and places only an identifiable new window; apps that reuse
an existing window may open without being repositioned, with an explanation.
Tiling respects personal layout exclusions. Browser-tab reuse for Gmail/GitHub
still uses the optional browser connection described below.

The bar dropdown has **Back**, **Forward**, and **Save view** controls for window
layouts. Skipper records settled changes to open windows, including positions,
sizes, workspaces, floating state, and fullscreen state. Back and Forward restore
earlier arrangements; closed windows are skipped. Save view records the current
arrangement immediately. History keeps up to 30 views for the current desktop
session and survives a Skipper restart. Making a new arrangement after going Back
replaces the Forward branch, like ordinary undo history.

### Update, disable, and remove

```bash
omarchy plugin update greg.skipper
# Re-run setup when dependency pins or shortcut integration change:
python ~/.config/omarchy/plugins/greg.skipper/plugin_setup.py install --shortcut --autostart
```

Quit Skipper from the bar, then click **Start Skipper** to load updated Python
code. The widget hot-reloads. Disabling the widget hides its controls; it does
not stop an already-running companion process. Use **Quit** first if desired:

```bash
omarchy plugin disable greg.skipper
```

To remove both the runtime integration and the widget, run these in order:

```bash
python ~/.config/omarchy/plugins/greg.skipper/plugin_setup.py uninstall
omarchy plugin remove greg.skipper
```

Uninstall stops the runtime, removes unmodified setup-owned launchers and its
shortcut block, and preserves recordings, learned phrases, settings, model,
Python environment, and backups. It reports modified files rather than deleting
them. Review the retained `~/.local/share/skipper` directory yourself if you
also want to remove saved data. No system packages are removed.

### Capabilities and privacy

Skipper reads window metadata, controls windows via Hyprland, launches installed
apps, and inspects terminal process trees for closing confirmations. The optional
browser connection can inspect and select browser tabs. Command history and old
recordings remain local. Skipper does not capture microphone audio or run speech
inference. The runtime runs with your normal user permissions.

## Development setup


```bash
python -m venv --system-site-packages .venv
python install_desktop.py
```

There are currently no pip dependencies; requirements files document this.
The GUI uses system GTK4, PyGObject and Cairo (`gtk4`, `python-gobject` and
`python-cairo` on Arch),
already present on this machine. System-site-packages exposes those bindings to
the environment without modifying installed system packages.
The launcher installer adds Skipper to your per-user application menu and creates
`~/.local/bin/skipper`. Keep the checkout at the same path after installation,
or rerun the installer if you move it. `launch.sh` also works directly.
## Use

Launch **Skipper** from the application launcher, run `skipper`, or use
`./launch.sh`. Press **Super + R** for the picker. Choose commands and arguments
with the dropdown, then press Enter. Escape cancels without running anything.

Click **Tutorial** in the taskbar dropdown for a guide, or open **Explorer** to
inspect commands, history, and settings. **Quit** finishes current work and stops
the runtime; **Start Skipper** restarts it. Closing Explorer does not stop Skipper.

The runtime always starts without a speech model. `SKIPPER_TEXT_ONLY` and the
installer's old `--text-only` flag are no longer needed. Voice input is planned,
not enabled by a setting in this version.

## Desktop commands

### Grammar and intent explorer

Open **Skipper Explorer** from the application launcher, run `skipper-explorer`,
or run `./launch-explorer.sh` from this checkout. `python install_desktop.py`
installs both Skipper and the separate explorer launcher.

The native GTK explorer has these views:

- **Grammar:** reusable patterns, their bindings, and every generated phrase.
- **Vocabulary:** canonical slot values, spoken forms, and rules using them.
- **Intents:** typed argument schemas and concrete structured meanings.
- **Try a command:** exact, learned-alias, and fuzzy parsing with candidate
  scores and rule evidence. Testing never executes actions or learns phrases.
- **History:** saved recordings/transcripts, playback, copying, and transcription retry.
- **Settings & phrases:** terminal-close preference and learned phrase removal.
- **Live windows:** terminal names injected into `<window>`, their generated
  commands, identities, and shared/ambiguous names; refreshed every two seconds.

The explorer uses the same catalog and parser as voice commands, without loading
the speech model or microphone. It reloads learned aliases for each inspection.
Grammar browsing is read-only: edit grammar definitions in
`command_catalog.py` and restart the apps to load changes. Context scopes,
grammar editing in the GUI, and paired intent history are later work in
[the plan](docs/intents-and-app-split-plan.md).

`RULES`, `VOCABULARY`, and `SCHEMAS` are the authored language definitions.
For example, `open <destination>` and `bring up <destination>` expand across
Gmail/GitHub and their spoken forms. Both emit a structured meaning such as
`{"type": "open_destination", "arguments": {"destination": "gmail"}}` (serialized
with `schema_version: 1`). Adding a pattern applies to every value of its
non-terminal; adding a vocabulary value applies to every rule using that slot.
Shared browser patterns now also accept “launch Chromium,” “focus Google
Chrome,” and the other combinations of existing browser names and patterns.

`grammar_engine.py` validates bindings and allowed argument values and rejects
conflicting phrases. It derives `EXPANSIONS`, `GRAMMAR`, and the compatibility
`INTENTS` view. Existing execution IDs and saved aliases remain supported.
Fuzzy candidates are grouped by the complete meaning, including destination and
targeting arguments, so different destinations still compete. A shared pattern
is distinct from an automatically learned alias, which maps one phrase to one
concrete intent. Voice status now includes the parsed intent.

### Command behavior

Named terminals are now a live vocabulary. Enter **“focus skipper,” “switch to the
skipper terminal,” “focus the monitor replug bug,”** or **“close the patch monitor
terminal.”** `WINDOW_RULES` defines `focus <window>`, `switch to <window>`,
`go to <window>`, `close <window>`, and `move <window> to the other screen`,
with optional “the.” Move also accepts “other monitor.”
The rules expand across the terminal windows captured when the picker opens.
New/renamed/closed terminals are reflected on the next recording without
restarting Skipper. Explorer's command tester fetches a fresh list on each test.

`window_vocabulary.py` extracts spoken forms from titles: task name, project
name, combined title, and terminal/window qualifiers. Task/project titles also
accept Codex qualifiers. It strips changing status prefixes and spinners; plain
terminal titles containing a directory also contribute that directory's final
name. Short task prefixes with a terminal/window/Codex qualifier work too,
such as “explain terminal” for “Explain Omarchy plugins.” Duplicate prefixes
remain ambiguous. This uses title conventions rather than reading terminal contents.

Exact and fuzzy matches produce `focus_window(window=<captured identity>)`.
Fuzzy matching checks both wording and the window name. Shared names remain
ambiguous: use the task title if multiple terminals belong to the same project.
A title can change after capture without changing the chosen target, but a
closed/replaced window will not be substituted. Dynamic window matches are not
saved as permanent aliases. Named close commands produce
`close_named_window(window=<captured identity>)` and use the existing terminal
running-program confirmation preference. Approval remains bound to the captured
window; a closed/replaced window is never substituted. Unmatched named-terminal
close requests do not fall back to closing the most recent terminal.
Named move produces `move_named_window(window=<captured identity>, monitor=other)`.
This live vocabulary covers terminal focus, close, move, and maximize.
“Maximize the explain terminal” produces a captured-window intent with
`monitor=current`. Custom nicknames are not included yet.

**Command mode is permanent.**
Enter one of these phrases in the command picker.
The selected wording resolves to an intent and its arguments. Confirmations and
captured-window identity checks still apply. Unknown input stays editable.
Typing does not save automatic speech aliases or create audio recordings.

Stable intent IDs, display labels, and built-in phrases are generated into `INTENTS` in
[command_catalog.py](command_catalog.py), beside the fixed website URL registry.
`GRAMMAR` is generated from the same rules. Browse **Grammar** in Explorer for
built-in phrases, or **Settings & phrases** to review aliases and **Forget** a mistake.
Aliases persist in the private SQLite database at
`~/.local/state/skipper/command-history.sqlite3` (respecting `XDG_STATE_HOME`).
Legacy `aliases.json` files are imported once and retained as private backups.
Personal data stays outside Git with owner-only permissions.
This teaches the command matcher; it does not retrain the speech recognition model.
Saved recordings remain available for playback; retranscription is retired.

| Allowed phrase | Action |
| --- | --- |
| move to other screen / move window to other screen | Move the window focused when recording started to the other screen |
| move the explain terminal to the other screen / move patch monitor terminal to the other screen | Move the named terminal captured when recording started |
| move chrome to the other screen / move twitter to the other screen | Move the most recently focused matching app window; also supports Chromium, Google Chrome, X, and Discord |
| open a new terminal / open a terminal / open terminal / open new terminal | Open a fresh default terminal window on DP-1 |
| open chrome | Launch Chromium or focus an existing browser window |
| bring up chrome | Launch/focus Chromium and maximize with tabs visible |
| launch chrome | Same |
| switch to chrome | Same |
| open chromium | Same |
| bring up chromium | Launch/focus Chromium and maximize with tabs visible |
| open google chrome | Same |
| bring up google chrome | Launch/focus Chromium and maximize with tabs visible |
| open gmail / bring up gmail | Bring up Gmail |
| open github / bring up github | Bring up GitHub |
| open x / bring up x / switch to twitter | Launch X’s installed app or maximize and focus its existing window; x and twitter work with these prefixes |
| maximize chrome / maximize chromium / maximize google chrome | Maximize the most recently used normal browser window |
| maximize discord | Maximize Discord’s app window |
| maximize x / maximize twitter | Maximize X/Twitter’s app window |
| close terminal / close the terminal / close a terminal | Close the most recently used terminal; ask if programs are running |
| close this terminal | Close the terminal focused when recording started; ask if programs are running |
| close this window / close the current window | Close the window focused when the command starts |
| close discord | Close the most recently used Discord app window |
| close x / close twitter | Close the most recently used X/Twitter app window |
| close chrome / close chromium / close google chrome | Close one normal Chrome/Chromium window, including its tabs |
| open discord / bring up discord / switch to discord | Launch Discord if closed, otherwise maximize and focus its existing app window |
| show all windows / show all open windows / show all open window | Restore and raise each open window on its own workspace |
| list open windows / list the open windows / what windows are open | Show every open window across all workspaces without changing its layout or focus |

All Skipper open/bring-up commands now use the same presentation policy: move the
selected or newly created window to DP-1, maximize it with normal controls visible,
explicitly raise it above the floating grid, and focus it. This includes browsers,
Gmail/GitHub browser windows, Discord, X, and new terminals. Enter **“tile open
windows”** afterward to include the new window in the equal grid.

Discord and X use their installed desktop launchers (the Omarchy web apps on
this machine).
X and Twitter are synonyms for one intent. Exact app classes identify their
windows; ordinary browser tabs titled Discord or X are not treated as app windows.

Maximize commands select one existing window, keep it on its current screen and focus it,
then set maximized mode for both the compositor and app. Normal browser controls
remain visible; this is different from fullscreen. Repeating the command keeps
it maximized. If the app is closed, Skipper reports that instead of launching it.

“Move to other screen” and “move window to other screen” work for any captured
window, including Chromium. The window moves to the other screen's active
workspace and receives focus. If it is the only window there, it is maximized;
otherwise the destination workspace's windows are arranged in an equal grid.
With more than two screens, the destination is
the next connected monitor in monitor-ID order. It reports an error if only one
screen is available. Fuzzy matches keep the original captured window as their target. A closed or replaced window is never substituted.

Named moves use the same behavior, relative to the selected window's current
screen. App moves select from the recording's captured windows and report an
error if the app is closed. They do not launch it. Unknown names never fall back
to moving the focused window. “Other window” is also accepted as “other screen.”

Terminal close commands close an idle shell prompt directly. If a program or job
is running, they show a confirmation in the bar popup with the chosen window's title.
The target is captured when the picker opens and remains fixed while the
confirmation is pending. “Close this terminal” does
nothing if the focused window was not a terminal. “Close terminal” chooses the
most recently used terminal across screens/workspaces. Only that window is closed.

**Confirm before closing a terminal with running programs** defaults on. Turn it off in Explorer’s **Settings & phrases** to skip
confirmation for terminal-close commands; the choice persists locally in
`~/.local/share/skipper/settings.json` (respecting `XDG_DATA_HOME`). Fuzzy matches follow the same running-program warning setting. Skipper inspects the terminal's process tree and foreground process group. A lone
interactive shell with no live child jobs is treated as idle; foreground commands,
background/stopped jobs, and directly launched apps count as running programs.
Unknown states (including shared terminal servers that cannot be resolved per
window) still ask. This detects processes, not unsaved work. Closing can stop them. Skipper sends a normal close request and leaves
any additional terminal/app confirmation to you; it never force-kills them.
If the selected window disappears or is replaced before approval, Skipper will not
close a different window.

Close commands send a normal window-close request to one matching window,
preferring the most recently used match across workspaces. They do not focus,
move, launch, or forcibly kill the app. If no match exists, Skipper says so.
An app may ask you to confirm closing; Skipper leaves that dialog for you.
Close commands work even without DP-1. “Close Chrome” closes the whole selected
browser window and its tabs; it excludes the separate Discord and X app windows.
Gmail/GitHub tab closing and arbitrary window-name closing are not included.

The explicit spellings “g mail” and “git hub” are accepted too.

Website commands now operate on **normal Chromium browser tabs**:

1. Find an HTTPS tab whose hostname exactly matches the registered site.
2. Reuse it without reloading. If there are duplicates, prefer the focused
   browser window, then the most recently accessed matching tab.
3. If no matching tab exists, create one in the focused normal browser window,
   or the most recently used normal window. Open a normal browser window if needed.
4. Activate the tab while preserving its browser window's workspace, size,
   fullscreen state, and tiling.

Private windows, standalone app windows from the earlier implementation, and
extension-only control windows are excluded. Existing app windows are left intact.
Pending navigations count as matching tabs to avoid duplicates during page loads.
Both “open” and “bring up” currently follow these same rules. A website request
is navigation, not a presentation request: it never moves, maximizes, tiles, or
fullscreens an existing browser. If Chromium is closed, Skipper launches it and
lets the compositor's normal new-window policy decide whether it fits the
current tile layout or opens on its own. Say an explicit browser layout command
such as **“open the browser and tile”** or **“open the browser in full screen”**
when that presentation is wanted.

Enter **“open another GitHub tab”** (or **“open a new Gmail tab”**) to create a
new tab even when that website is already open. This is a separate intent from
**“open GitHub,”** which always prefers reusing an existing matching tab.

Tab control uses the already installed Playwright extension (0.4.0) and the pinned
local Playwright MCP runtime from `codex-browser-tools` (0.0.80). Skipper sends fixed
JavaScript to the extension's tabs API; no AI agent interprets or runs commands.
The local connection is stored at `~/.config/skipper/browser-connection.json`, with
mode 0600, using the installed runtime's `command`, `args` (including `--extension`),
and `env`. The existing extension connection token remains outside this repo.
This machine is configured; other installations need their own extension connection.
Skipper keeps a connection open after the first website command; an extension control
tab supports that connection. Closing Skipper stops its connection process.
A connection failure reports an error rather than opening duplicate fallback tabs.

The intended multi-browser selection and clarification policy is documented in
[Website routing and browser resolution](docs/browser-site-routing.md). The
current adapter is Chromium-only; the document distinguishes its existing
reuse/new-tab/new-window behavior from the planned “which browser?” flow.
Notes from the reviewed voice-app reference clones, including a deterministic
tab-switching recommendation, are in
[Browser and tab notes](docs/other-voice-app-browser-notes.md).

To add a website, add its fixed HTTPS URL, display name, and exact hostname to
`SITES`. The destination vocabulary and schema include it automatically; all
destination rules generate its phrases and `site:<key>` execution ID. Add any
extra spoken forms in `DESTINATION_FORMS`. No wildcard domain command
is enabled. Tab-selection rules live in `browser_tabs.js`, using the documented
[Chrome tabs](https://developer.chrome.com/docs/extensions/reference/api/tabs)
and [windows](https://developer.chrome.com/docs/extensions/reference/api/windows) APIs.

Exact matching lowercases, collapses whitespace and removes surrounding
sentence-ending `. ! ?` punctuation. Fuzzy suggestions use Python's standard
library text similarity, scoring built-in and learned phrases and grouping them
by intent. A suggestion needs at least 0.72 similarity and a 0.06 lead over the
next intent; ambiguous matches, explicit negation, single-word fragments, and long dictation are skipped.
These are initial heuristics, not confidence probabilities; some mishearings may
still produce no match or choose an incorrect intent. Accepted fuzzy matches run
and are remembered automatically.
No extra model or dependency is needed. Website destinations and OS actions remain
fixed; speech cannot supply a URL, shell command, or browser argument.

The OS adapter reads Hyprland's window list, focuses an exact browser class, or
launches the installed browser desktop entry. It excludes Chromium-hosted web
apps such as Discord. On this installation, “Chrome” maps to Chromium.

### Two-screen layout on this MacBook

The command popup belongs to the bar on the monitor focused when the picker opens.
It occupies no workspace or tile. Voice actions retain their existing display
policies: open/focus app commands target **DP-1**, all maximize commands
stay on the target's current screen, and move-to-other-screen selects another
monitor and arranges the destination workspace.

The old GTK-window rule in [config/hyprland-skipper.lua](config/hyprland-skipper.lua)
only applies to the development window; the runtime creates no such window.

## Historical speech experiments

Earlier versions used a direct Parakeet/ONNX integration. That code and its
inference dependencies have been removed. [Early measurements](docs/first-run.md)
remain historical reference, not current setup instructions. Downloaded model
files and recordings are left intact.

## Command picker and history

**Super + R** opens a centered written-command box on the active monitor.

The box shows supported commands from the shared intent dataset and commands
generated for currently available apps and windows. Typed and spoken phrases are
never added to this list. Type a fragment such as `tile term` to fuzzy match
“tile the terminals.” Up/Down selects a match. Tab accepts a selection or opens
its next argument level; Shift+Tab goes back. Add step queues a completed command.
Enter runs the complete selection and any queued steps. Incomplete commands ask
for their remaining arguments.
Escape cancels. Selected wording is parsed against the current desktop context;
old window addresses are never replayed. Normal confirmation rules still apply.

History is private local data (PII), stored in
`~/.local/state/skipper/command-history.sqlite3` (or `$XDG_STATE_HOME/skipper/`).
The directory is owner-only (0700), and the database is owner-only (0600).
It is outside the checkout; Git ignores databases and sidecars as a safeguard.
Every recognized invocation, including repeats from speech and typing, is saved.
The dropdown searches two sources: base commands from the shared dataset and
dynamic commands for currently available apps and windows. Newly supported
intents appear when the dataset or dynamic vocabulary changes. Opening the box
captures current targets and rebuilds the dynamic source. While open, it refreshes
available targets every half-second. Saved command history is never searched by
the dropdown.
For example, a uniquely named terminal can contribute “close the skipper terminal,”
“focus the skipper terminal,” “maximize the skipper terminal,” and “move the skipper
terminal to the other screen.” Wording comes from dataset templates; titles and
expanded phrases stay local. Ambiguous window names are excluded.

The list shows up to ten plain command phrases. Typing filters both supported
sources by ordered-letter subsequence matching, including alternative wording.
The cheap filter permits skipped letters in the candidate. A shortlist is then
ranked by text similarity alone; frequency is reserved for later tuning.
See the matching notes for the exact algorithm.
Refresh preserves your draft and the original focused window; named targets use
the latest displayed snapshot. Execution checks the captured identity again, so
a closed or replaced terminal is not retargeted.
Suggestions do not create command-history rows until used.
The original diagnostics log is imported once, including older entries; no fake
history is seeded. Rows record recognition attempts, not verified execution:
failed or cancelled actions may appear in the database.
Recordings and existing diagnostic logs remain separate local private data.
The picker stays open while you type. Escape cancels; incomplete commands do not
run. Opening it captures the active window, so “this window” refers to your app.
Typed input does not apply speech corrections or save automatic speech aliases.
Future speech input will share command parsing, argument selection, and confirmation.
The optional shortcut source is `config/hyprland-skipper-written.lua`; check for
conflicts before installing it elsewhere. Skipper must be running for the shortcut.

Type the command you meant in the single field, click **Check meaning**, then
**Save**. An unclear typed command stays editable with an explanation. Saving
remembers the exact heard phrase for next time and does not run it immediately.
The original transcript remains intact; the typed wording and interpreted action
are saved separately. Previously saved three-layer corrections remain compatible.
Cancel saves nothing. Starting a new recording invalidates the old request.

Tiling defaults to **side by side (left to right)**, using a grid for larger groups, on the monitor
of the active window captured when the picker opens. Paired commands bring the
selected second window to that workspace. Five windows use two columns over
three rows, with every window the same size and one unused cell. Incomplete
rows retain the same cell dimensions. The layout respects scale, rotation,
bar space and gaps; too many windows to fit at a usable minimum size produce an
error.

Open **History** in Skipper's taskbar dropdown to review recent recordings in three
columns: **what was heard**, **words you meant**, and **intended action**. Each row
also shows the original logged match and outcome, when available. Edit the words,
choose an action from the searchable list, and click **Save correction**. **Match
these words** can suggest an action; saving still requires your click and never
runs the action. Use **Refresh** to reload history.

User corrections are separate from automatic fuzzy aliases. They apply before
normal matching only when the normalized heard phrase is identical (ignoring case
and punctuation), including commands normally excluded from automatic learning.
These saved speech corrections are retained for future voice input; typed commands do not apply them.
**Remove correction** restores normal parsing. The picker currently covers the
fixed command catalog; it does not save identities of individual named windows.
Corrections and their edit/removal audit are saved outside the repo in
`~/.local/state/skipper/command-history.sqlite3` (under `$XDG_STATE_HOME` if set).
Legacy `corrections.json` files are imported once and retained as private backups.
Original audio/transcripts are not overwritten when correcting a command.

Command diagnostics are stored outside the checkout at
`~/.local/state/skipper/commands.jsonl` (or `$XDG_STATE_HOME/skipper/commands.jsonl`).
Each line is a timestamped JSON event linking the recording file, focused window
context, recognized transcript, original parse result (including candidates and
matching method), and action outcome or error. Unrecognized commands are logged
too. Audio and transcript files remain in `~/.local/share/skipper/recordings`.
Logging covers submitted commands; Skipper does not listen to conversations.
Use `tail -n 30 ~/.local/state/skipper/commands.jsonl` to inspect recent events.

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_browser_tabs.cjs
.venv/bin/python tests/explorer_smoke.py
.venv/bin/python tests/history_smoke.py
.venv/bin/python tests/correction_smoke.py
.venv/bin/python tests/tutorial_smoke.py
.venv/bin/python tests/bar_popup_smoke.py
.venv/bin/python tests/terminal_activity_smoke.py
.venv/bin/python tests/window_close_smoke.py
.venv/bin/python tests/tile_windows_smoke.py
.venv/bin/python tests/window_close_smoke.py --maximize
.venv/bin/python tests/window_close_smoke.py --maximize-current
.venv/bin/python tests/window_close_smoke.py --maximize --move
```

Enter **“maximize this window”** to maximize the window focused when the picker opens,
on its current screen. Repeating the command keeps it maximized; browser tabs
and normal window controls stay visible.

Enter **“tile open windows”** (or **“tile all windows”**) to arrange the windows
on the workspace focused when the picker opens in equal-sized grid cells (four
windows form a 2 × 2 grid). It exits maximize/fullscreen and separates groups.
The adapter uses positioned floating windows to avoid inheriting old split ratios,
respects monitor scaling and the panel, and leaves spare cells empty for odd counts.
Run the command again after opening or closing windows to rearrange the grid.
Skipper is excluded. Other workspaces stay as they are; repeating the command keeps
the windows tiled.

Enter **“tile all the terminals”**, **“tile all terminals”**, or **“tile terminals”**
to tile only terminals on that workspace and hide the other apps. **“Tile all
browsers”** shows browser windows and hides everything else; **“tile all apps”**
shows all non-terminal apps and hides terminals. **“Tile all windows”** brings
the hidden windows back and tiles everything together. These commands include
windows hidden by an earlier tiling command on the same workspace, so you can
switch between terminals, browsers, apps, and everything repeatedly.
Skipper and other workspaces are excluded. If no matching windows remain, nothing
is hidden. Hidden windows stay open in a dedicated special workspace associated
with their original workspace. The `tile_terminals`, `tile_browsers`, and
`tile_apps` intents are available in the command catalog and Explorer.
The apps command uses **“tile all apps”** and **“tile the apps”** as its built-in phrases.
Similar wording competes with other intents using the usual score threshold and
winning margin. Learned aliases remain disabled for this intent so old wording
cannot bypass scoring.

**“Hide all terminals”** hides visible terminals; **“hide all apps”** hides
visible non-terminal apps. Both accept only those exact phrases (ignoring case
and punctuation). They leave the remaining windows in place and do not bring
back previously hidden windows. **“Tile all windows”** restores and tiles them,
even after hiding the last window on a workspace.
**“Hide this window”** and **“minimize this window”** hide just the window focused when the picker opens,
whether it is a terminal or another app. It also requires the exact phrase and
can be restored with **“tile all windows”**. A focus change while speaking does
not change the target; a closed, moved, or replaced window is skipped.

### Menu-bar runtime

`launch.sh` starts `runtime.py`, a windowless `Gio.Application` retaining the
existing application ID and push-to-talk D-Bus actions. The user-owned
`config/skipper-bar` widget renders a passive attached popup. Runtime state lives
privately under `XDG_RUNTIME_DIR`, including transcript, intent, amplitude samples,
and a per-confirmation token. Stale or repeated confirmation tokens cannot act on
a later command. The widget detects a stopped/unresponsive runtime.

`install_bar.py` installs the widget under `~/.config/omarchy/plugins/greg.skipper`,
updates the user shell layout, and installs a login launcher. Existing plugin
files and shell config are backed up. Packaged Omarchy files are unchanged.
Plugin changes normally reload automatically; `omarchy restart shell` can apply
a change if this shell version retains the previous component in its cache.

### Tile two specific windows

The written-command selector offers **“tile this window and the …”** for each
other open window, using the same live window names as focus, close, hide, and
minimize. It does not offer the current window as its own partner. The list
refreshes when windows open or close, and a selected pair is checked again
before tiling.

For example, say **“tile this window and the chromium window”** when that window
is open. “This window” comes from the focus captured when the picker opens.
If a name still matches several windows, a picker shows their titles and workspace
numbers. Choose a button to continue, or cancel. Starting a new recording cancels
the pending picker. Spoken answers to picker questions are not yet supported.

The selected pair is tiled side by side on the original workspace and screen:
the original focused window on the left, the chosen window on the right. The chosen
window is brought there if needed. All other windows on that workspace are hidden.
They remain running; “tile all windows” restores
them. Other workspaces are left in place.
Both references must identify different windows. Missing matches or windows that
closed, moved, or changed identity stop the command with an explanation.

The reusable resolver in `window_resolution.py` handles each intent argument
separately and asks only about ambiguous references. It also accepts “the
terminal”, browser names, and exact spoken window titles; for example, “tile the
terminal and the browser” can ask about either slot. Resolution retains the
original capture through every question. Terminal nicknames can be added as
another reference source without changing the picker or tiling action.

### Close a particular app window

**“Close all tabs”**, **“close all browser tabs”**, **“close all tabs in the
browser”**, or **“close all tabs on the browser”** clears the selected browser
window and leaves one active `about:blank` tab. **“Close the browser”** still
closes the window itself. Tab clearing uses the visible-browser uniqueness
rule below and asks which window when ambiguous. It brings the selected window
forward, creates the blank tab first, and closes its previous tabs, including
pinned tabs. Other browser windows are left alone.

Tab clearing requires Chrome/Chromium and the configured local browser extension
connection. Unsupported browsers, private windows, stale targets, and mismatched
focus stop the command. A connection error may happen after some tabs closed;
Skipper reports it and does not automatically retry. It does not inspect page
contents or send browsing data to an LLM. These phrases require an exact match.

Enter **“close Tensaku”** or **“close image viewer”** to close the Tensaku
screenshot annotation app. Both names target its exact app identity; browser
pages with those titles are not selected. Multiple Tensaku windows produce
the same window picker described below.

Say or type **“close the browser”**, **“close the X window”**, or
**“close the file browser window”**. “Close the file manager window” and
“close Files” also target Nautilus. X matches the installed X/Twitter app,
not a browser tab whose title happens to mention X.

A single matching window closes directly. If several match, Skipper asks which
window to close and lists their titles and workspaces. Cancel leaves them open.
The chosen window's identity is rechecked before closing. An app's own unsaved
work confirmation can still keep its window open.

### Open the browser with a layout

For **“the browser”**, Skipper first considers browser windows visible on your
displays when you start the command. One visible browser is selected even if
others are hidden; several visible browsers produce a picker. With none visible,
one open browser is selected, or several hidden browsers produce a picker.
If visibility information is unavailable, Skipper considers all browser windows.
This applies to opening, closing, and browser tiling commands. Opening a hidden
browser brings it onto the captured workspace; closing targets the selected
window. Window identity is checked again before acting.

Chromium is the default browser Skipper launches when none is open. Common
misspellings such as “brwoser” are accepted in these opening commands.

- **“Open the browser and tile”** reuses an open browser, or launches Chromium
  if none is open. It puts the originally focused window on the left and the
  browser on the right, hiding the other windows on that workspace.
- **“Open the browser in full screen”** opens or reuses a browser in true
  fullscreen on the captured workspace.
- **“Open the browser”** defaults to fullscreen.

If browser selection is ambiguous, choose one in the picker. The tiling command keeps
its original focused window even when launching the browser changes focus.
Both commands work through the centered typing box.


### Volume, brightness, and media

These commands work through the centered typing box. They accept the
listed wording exactly; they are not guessed from similar phrases.

| Say or type | Action |
| --- | --- |
| volume up / turn the volume up / louder | Raise output volume by 5 percentage points, capped at 100% |
| volume down / turn the volume down / quieter | Lower output volume by 5 percentage points |
| mute / mute sound | Set output mute on |
| unmute / unmute sound | Set output mute off |
| brightness up / increase brightness / brighter | Raise brightness on the captured display |
| brightness down / decrease brightness / dimmer | Lower brightness on the captured display |
| play music / resume music | Request playback from the desktop media service |
| pause music / pause playback | Request pause |
| next song / next track | Request the next track |
| previous song / previous track | Request the previous track |

Mute and unmute set the requested state, so repeating either does not toggle it.
Volume uses Omarchy's output routing, including its physical-sink resolution for
DSP outputs. Its volume adjustment also unmutes output, matching the desktop's
volume keys. Brightness uses Omarchy's hardware-aware increments (smaller near
minimum brightness); changing focus after starting a command does not retarget it.
Media actions report an error when no player handles the request. These commands
require the installed Omarchy audio/brightness commands, `pactl`, and the Omarchy
shell media service; errors appear in Skipper's normal status display.

### Named actions

Open **Skipper Explorer → Named actions** to create, edit, or remove a named
shortcut. Enter a name and an exact phrase, choose a supported action, review its
meaning, then save. For example, **Quiet time** can map **“make it quiet”** to
**Mute sound**. Saving never executes the action. The phrase works immediately
through typed input and Explorer's parse-only preview.

Named actions select one existing typed command. They retain its window picker,
original captured context, and terminal-close confirmation. They do not contain
shell scripts, schedules, or chains of commands. Built-in phrases, duplicate
phrases, negations, and phrases already used by learned aliases or speech
corrections are rejected. Custom phrases are exact-only and are never trained by
fuzzy matching. Use **Edit** to change an existing action and **Remove** to forget it.

Actions live in their own namespace in the private SQLite database at
`~/.local/state/skipper/command-history.sqlite3` (respecting `XDG_STATE_HOME`).
Writes are transactional and owner-readable/writable. Malformed data or a changed
saved intent stops parsing with an explanation instead of executing an unintended
meaning. Legacy `actions.json` files are imported once and retained as private
backups. Back up the database with your other Skipper user data.

These features were inspired by [Genesis](https://github.com/ronald2wing/Omarchy-Genesis)
and implemented in Skipper's own grammar, executor, and Explorer. No Genesis code
or dependencies are bundled.

### Open installed apps

Skipper reads the visible `.desktop` launchers in your XDG application directories
each time it interprets a command. Say or type **“open LocalSend”**, **“launch
Moonlight”**, or **“open Document Viewer”** to launch one of those apps. The
Explorer's **Installed apps** page lists the names currently available and their
exact command phrases.

This discovery is exact-only: Skipper does not fuzzy-match app names, learn them,
or use an app name as a window title. It excludes hidden launchers, terminal
emulators, entries whose `TryExec` program is absent, D-Bus-only entries, and
names shared by more than one launcher. Existing Skipper wording keeps priority;
for example, **“open Chrome”** remains Skipper's browser command. If an app is
installed, removed, renamed, or hidden, the next command sees the new state.

Skipper launches the selected desktop file through `gio launch`, without passing
speech text as shell arguments. It reports that the launcher started; applications
whose desktop files do not create a normal window may still manage their own
startup or show an error separately.

Open windows contribute focus, close, hide, and minimize commands to the
written-command selector. A single Firefox window, for example, offers
**“focus the firefox window,” “close the firefox window,” “hide the firefox
window,”** and **“minimize the firefox window.”** Hide and minimize perform the
same action. Already hidden windows offer focus and close. Multiple windows of
one app receive distinct window names. These commands check the captured window
identity before acting; they never launch a closed app. Open commands continue
to list launchable installed apps.
If floating windows cover a tiled target, focus moves the target into the
floating stack so it actually comes forward without maximizing it. This also
applies when choosing a window from Skipper's window list.
Ambiguous spoken names ask for a more specific window title; selector entries
use phrases that resolve to one open window. Skipper-hidden windows are restored
to their original workspace when focused.

## Shared dataset and private SQLite overrides

See [data ownership, lookup precedence, migration, and installation](docs/data-ownership.md).
The dataset is maintained at https://github.com/gregorycoppola/omarchy-voice-dataset.
Each Skipper release includes its compatible snapshot in `bundled/intents`; users
install only Skipper. `OMARCHY_INTENT_DATASET` is an explicit developer override.
Personal aliases, corrections, named actions, and preferences now use the same
private SQLite database as command history. Legacy JSON files are migration backups.

### Close all terminals

Say or type **“close all terminals”**, **“close all terminal windows”**, or
**“close every terminal”**. This targets terminal windows across all workspaces,
including hidden terminals, captured when the command starts. Other apps and
terminals opened afterward are excluded. The shared wording and canonical
`window.close(target={kind: "all", value: "all_terminals"})` binding live in the
intent dataset.

This command requires an exact supported phrase. With terminal-close confirmation
enabled, Skipper asks once before closing the batch if any terminal has running
programs or its activity is unknown. Cancel closes nothing. Normal close requests
preserve each terminal application's own prompts; Skipper does not force-kill
processes. Window identities are rechecked before closing. If a close fails partway
through, Skipper reports how many close requests preceded the failure.

### List terminal names

Say or type **“list the terminals”** to show terminal windows across workspaces.
Each row shows its current title, terminal app, workspace, and up to three unique
spoken names derived from that title. Task/project titles and directory names can
provide names; changing status prefixes are removed. Shared names are omitted
when they identify multiple terminals. Unnamed terminals remain clickable.

These are live title-derived names, not permanent nicknames or terminal contents.
For example, `Fix layout | skipper` can supply “fix layout” and, if unique,
“skipper.” Use a name with existing commands such as “focus fix layout.” Clicking
a row focuses the same window after checking its identity again.

### Quick Yes/No confirmation

Terminal-close confirmation appears in a centered popup with large **Yes** and
**No** buttons. **Enter / Y** confirms; **Escape / N** cancels. Key-repeat events
are ignored. Confirmations retain the captured target and reject stale answers.
Voice confirmation can be added with the future speech adapter.

### Build a command sequence with Tab

Type **“open chrome”**, press **Tab**, then type **“tile the windows”** and press
**Enter**. Skipper opens Chrome, waits for that action to finish, then tiles using
fresh window information. Tab only queues a step; it executes nothing. Numbered
steps have a Remove button. Enter with an empty input runs the queued steps.
Escape discards the draft sequence. Up to 20 steps are accepted.

All steps must parse before execution starts. A confirmation or window picker
pauses the sequence; confirming continues it. Cancellation or an error stops the
remaining steps, while completed actions remain done. Each executed step is saved
separately in local history. Named-window commands retain their expected identity;
changed or replaced targets stop the sequence instead of redirecting the action.

### Hide an app window

Say or type **“hide Chrome”**, **“hide Chromium”**, **“hide X”** / **“hide Twitter”**,
or **“hide the browser.”** Chrome wording targets Chrome/Chromium specifically;
X wording targets the X app window, not a browser tab. Multiple matches show the
existing window picker. Hiding uses Skipper's holding workspace and leaves the
app running. Use **“tile all windows”** on its original workspace to restore it.
These commands require an exact supported phrase and work in command sequences.

### Show an app window

**“Show Chrome”** / **“show Chromium,” “show X”** / **“show Twitter,”** and
**“show the browser”** select an existing app window. A Skipper-hidden window is
restored to its original workspace, raised, and focused. Already visible windows
are raised and focused without resizing. Multiple matches show a picker, including
hidden browser candidates. If the app is closed, use its open command to launch it.
Show commands also work as steps in a command sequence.

**“Show all browsers,” “show all X,” “show all terminals,”** and **“show all
windows”** restore and raise every matching open window without a picker.
Chrome, Firefox, Discord, file managers, Tensaku, and apps are also supported;
“apps” excludes terminals. Each window stays on its own workspace, with
Skipper-hidden windows restored to their original workspace. The most recently
used match is focused last. Closed apps are not launched, and window sizes stay
unchanged. Use “tile all windows” to arrange windows side by side.

**“List all browsers”** (also “list browsers” or “list all browser windows”)
shows a clickable list of open browser windows across workspaces, including
Skipper-hidden browsers. It does not focus anything until you select a window.
“List all X” or “list all Twitter” lists X/Twitter app windows. Empty lists
explicitly say there are no open browsers, X windows, terminals, or windows.
Lists and window-selection prompts appear in the center of the monitor, like
the typed-command box, and take keyboard focus immediately. Enter closes an
informational list by default; Tab moves to a window and Enter selects it.
Selection prompts focus their first choice. Escape closes or cancels the popup.
The shared typed patterns “list all <application>” and “show all <application>”
also accept exact live app class names (for example, Spotify), with the app
name stored as an intent argument. Unknown app names produce an empty result.

Idle shell titles such as `alex@workstation:~/Projects/demo` are suggested as
**“close the shell alex projects demo.”** The hostname is omitted; the username
and directory path identify the shell. Task/project terminals retain their task
names. This is inferred from the shell-style title, not a check that no process
is running; normal terminal-close confirmations still apply.

### Personal layout exclusions

The private SQLite settings document supports `layout_excluded_classes`, a list
of exact Hyprland app classes (matching either class or initialClass). Excluded
windows remain in window listings, but Skipper skips them when tiling or hiding
windows and rejects direct move/maximize requests. This also protects overlays
when tiling terminals would otherwise hide other apps. Rules are read on every
layout operation; an empty list is the default for a new user. Changing an
overlay application's class requires updating its rule.

Use `Settings(DEFAULT_DATA / 'settings.json').set_layout_excluded_classes([...])`
from the Python API (`settings.Settings`, `personal_store.DEFAULT_DATA`).
These preferences live outside Git in the same owner-only SQLite database as
command history. Updating terminal-close confirmation preserves the rules.
The shared dataset also accepts “list all windows” and “list all the windows”.

### Tile a particular monitor

Say/type “tile the terminals on monitor 2” or “tile terminals on screen two”.
The same forms work for windows, browsers, and apps, with numbers 1–8.
Numbers are **one-based ordinals of connected, enabled, non-mirrored monitors
sorted by compositor ID**, not raw Hyprland IDs; reconnecting displays can change
the numbering. The response includes the monitor's connector name.

This tiles the selected monitor's active regular workspace, including windows
previously hidden by Skipper from that workspace. It does not gather windows
from other workspaces. Category tiling hides other apps on that workspace,
while personal layout exclusions remain untouched. Missing monitors produce an
error. Shared grammar and the optional canonical `window.tile.monitor` argument
live in the intent dataset; this executor resolves the live monitor at execution.

### Screen recording

“Start a new screen recording with web cam capture” starts Omarchy fullscreen
capture with webcam. “Start a new screen recording without web cam capture”
records the screen without webcam. Both include microphone audio and also accept
“webcam” as one word. The shorter “Start a screen recording” still includes webcam.
“Stop recording” stops the screen recording and lets Omarchy
finish saving it. Both work in the typed command box and through the normal
voice-command shortcut when a speech model is loaded; this is not an always
listening stop phrase. Keyboard-only mode does not recognize spoken commands.

An already-running recording is not toggled off by “start”. Repeated commands
are blocked while this session's recording command is starting or saving.
Stopping can control an Omarchy recording started outside Skipper too.
Skipper reports that saving is in progress, rather than claiming the file is
already finalized. Omarchy owns encoding, output location, and save notifications.

The optional personal SQLite setting `screen_recording_monitor` selects a
connector name before recording. Configure it with
`Settings(DEFAULT_DATA / 'settings.json').set_screen_recording_monitor(name)`;
`None` uses the focused monitor. A disconnected preferred monitor is an error.
The shared dataset owns both intents and their ten phrase variants; no personal
connector names or recording files belong in Git.

### Move to a workspace

“Move this window to workspace 3” moves the window captured at the start of the
command to that numbered workspace. The current workspace stays selected.
Digits are accepted for positive workspace numbers; spoken “one” through “ten”
also work. The move checks the original window identity and verifies its final
workspace. A grouped window is detached first so only that window moves.

### Switch workspaces

“Switch to workspace 3” changes the focused monitor to workspace 3, without
moving any windows. “Go to workspace 3” is also accepted. Workspaces 1–10 each
have a clean suggestion in the Super + R command list, so typing
“switch workspace” can find them. Spoken number words one through ten work too.

### System operations

Say or type “sleep” / “suspend,” “screensaver,” “lock,” “log out,” “reboot,” or
“shutdown.” These appear in the typed command suggestions and use the same
operations as Omarchy's System menu. Logout, reboot, and shutdown show a focused
confirmation before ending the session; Enter/Y confirms and Escape/N cancels.
Sleep suspends directly. System actions require exact supported wording, and
end a queued command sequence. Skipper reports a request, not proof that the
machine has finished suspending or shutting down.

### Open URL

Say or type “open URL” to show a URL entry box. Type or paste a web address,
then press Enter to open it in your default browser, or Escape to cancel.
Addresses without a scheme use HTTPS. Invalid addresses stay in the box for
correction. The box accepts addresses directly, without command suggestions.

“Open a new browser to web site” opens a second, focused website picker on the
same monitor. Its suggestions now come automatically from browser history:
visits to individual pages are summed per hostname, with the most visited sites
first. Equal counts use the latest visit, then hostname. Chromium, Chrome, Brave,
and Firefox profiles in the usual local directories are supported. Up to 100 sites
are retained in memory; the picker filters these and shows at most ten at a time.
You can always enter a new address. **Open website in new browser…** and
**Open website in existing browser…** are complete choices under **open**: Tab opens
site choices; Tab accepts a site and Enter opens it. Existing browser uses a new tab
in the captured connected Chrome/Chromium window; multiple possible windows add
a browser-choice level. Shift+Tab goes back. Existing-window mode requires the
configured browser extension connection and never falls back to a new window.

History loads on a background thread when the website picker opens, with a
60-second in-memory cache and a **Refresh browser history** button. A locked
Chromium database is read from a private, disposable snapshot including its WAL
or rollback journal; an unstable or unreadable source is reported in the picker.
No browser files are modified. Suggestions contain site origins and visit counts,
not individual page paths, queries, or titles. Counts reflect retained history;
multiple profiles, including synced profiles, contribute their recorded counts.

Saved bookmarks remain stored and can still be managed, but they do not seed or
boost the most-visited list. This website-frequency order is independent of the
command picker's text-only ranking.

Saved websites and up to 20 recent destinations live in the personal
`websites.json` namespace inside `~/.local/state/skipper/command-history.sqlite3`,
with user-only permissions. No personal website JSON file is written and the
store refuses paths inside a Git checkout. The starter Twitter/X bookmark can
be edited or removed.

### Select an audio device

In the command picker, choose **Switch → audio output** or **Switch → microphone**,
then choose a device. Tab accepts the device; Enter sets it as the system default.
The current default is marked in the list. Back cancels selection.

Devices load when the level opens and refresh while it is visible. Switching the
microphone does not start recording or voice recognition. Existing applications
may retain their own audio routing. Audio selections cannot yet be queued with
Add step. Requires the local PipeWire/PulseAudio service and `pactl`.

### Find and open a file

Choose **Open → file**, to see recently opened files, newest first. Type a filename to search instead. Files
under your home directory are searched asynchronously; hidden files, ignored
paths, `node_modules`, and Python virtual environments are excluded. Folder
subtitles distinguish matching filenames.

Tab accepts a result and Enter requests opening it in the default application.
Search considers up to 80 candidates before picker ranking, so narrow broad
queries to find more specific results. File contents are not searched, and file
selections cannot yet be added to a command sequence. Requires `fd` and `xdg-open`.

The empty file menu merges desktop recent-file history (`recently-used.xbel`)
with Skipper's own opening requests, deduplicated by path. It uses recorded access
times, not filesystem modification times. Missing and hidden files are omitted,
and results stay within your home folder. Applications that do not report desktop
recent files may be absent. Skipper stores its additions locally in
`~/.local/state/skipper/recent-files.sqlite3` (or `XDG_STATE_HOME`); this history is
not stored in the repository. A launch request does not prove an app displayed
the file successfully.

### Explicit system controls

- **Enable / Disable → night light, Wi-Fi, or Bluetooth** sets the requested state.
- **Connect / Disconnect → paired Bluetooth device** operates on a known device.
- Rows show current state and refresh while browsing. Tab accepts; Enter applies.
  Selecting an already satisfied state leaves it unchanged.

Night light uses Omarchy's 4000 K / 6500 K settings. Wi-Fi changes the software
radio state; hardware radio blocks still apply. Bluetooth adapter choices are
separate on systems with multiple adapters. Pairing new devices stays in the
existing Bluetooth settings. System controls cannot yet be queued with Add step.
