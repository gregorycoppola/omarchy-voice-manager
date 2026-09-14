# Keety

Current release: **0.1.0**. This checkout includes **0.2.0-dev** voice-command
work. See [the changelog](CHANGELOG.md).

Planned direction: [structured intents, grammars, contexts, and separate voice
and management apps](docs/intents-and-app-split-plan.md).

A local voice-command app for an M2 MacBook Pro running ARM Linux / Omarchy.
Keety lives in the menu bar: hold-to-talk opens a compact popup with microphone
levels, recognized words, and the parsed intent. A windowless background process
handles speech and actions. **Keety Explorer** is the separate native app for
language inspection, recording history, learned phrases, and settings.

Uses NVIDIA Parakeet TDT 0.6B v3 through a community INT8 ONNX conversion and
`onnx-asr`. Inference runs on the CPU. No NVIDIA GPU, cloud transcription,
PyTorch, system package updates, or macOS frameworks are required.

## Setup

```bash
python -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/python keety.py download
python install_desktop.py
```

Tested dependency versions are in `requirements.lock` (Python 3.14, Linux
aarch64). `requirements.txt` records the direct dependency.
The GUI uses system GTK4, PyGObject and Cairo (`gtk4`, `python-gobject` and
`python-cairo` on Arch),
already present on this machine. System-site-packages exposes those bindings to
the environment without modifying installed system packages.
The launcher installer adds Keety to your per-user application menu and creates
`~/.local/bin/keety`. Keep the checkout at the same path after installation,
or rerun the installer if you move it. `launch.sh` also works directly.
The model download is pinned by revision in `model-manifest.json`; large weight
files are SHA-256 verified. Model files occupy about 639 MiB and stay in ignored
`models/`. Model download and dependency installation require internet access.

## Use

Launch **Keety** from the application launcher, run `keety`, or use
`./launch.sh`. Install the menu-bar widget and login launcher with
`.venv/bin/python install_bar.py` (the installer backs up existing user config).

**Hold Super/Command + R to speak; release either key to transcribe.** A compact
popup opens from the Keety bar indicator on the focused monitor. It shows actual
microphone amplitude, then the recognized words and parsed intent. It does not
join the tiling layout or grab keyboard focus. Recognition completes after
release; words do not stream during recording.

After a successful action the popup closes **immediately**. The latest readable
intent name stays to the **left of “Keety”** in the menu bar until another intent replaces it.
Unrecognized commands remain visible for 2.5 seconds and errors for six seconds.
Terminal-close confirmations stay in the popup until answered or superseded by
a new recording. Click the bar indicator to inspect the latest result manually;
click it again or use × to dismiss. **Explorer** opens the separate management
app. **Quit** finishes any current work and stops the runtime; **Start Keety**
restarts it.

There is no main desktop window. Closing Explorer does not stop recording or
commands. `./launch.sh --show` requests the voice popup from an existing runtime.
The previous GTK voice window remains in `gui.py` for development checks only.

Takes are limited to 30 seconds. A quick tap never toggles recording on. Releasing
R or either Super key stops capture even if focus changes. The shortcut renews a
200 ms recording lease; a lost release or compositor reload stops capture within
about 700 ms. Late renewals cannot restart it. Wait for transcription/action
completion before another take.

The installed shortcut is `~/.config/hypr/keety-ptt.lua`, loaded by
`~/.config/hypr/bindings.lua`; its source is
[config/hyprland-keety-ptt.lua](config/hyprland-keety-ptt.lua). It uses physical XKB
codes for R (27) and left/right Super (133/134), sending typed D-Bus actions to
the runtime. The desktop/bar installers do not install that shortcut.

Audio (`.wav`), transcripts (`.txt`), and timing metadata (`.json`) are saved in
`~/.local/share/keety/recordings/` (respecting `XDG_DATA_HOME`). Explorer's
**History** offers playback, Copy text, Transcribe again, and Open folder. Retry
requires a ready Keety runtime and never executes or learns a command. Audio is
retained if transcription fails. Files remain until you delete them; nothing is
automatically pasted into another application.

For the command-line interface:

```bash
# A mono, 16-bit PCM, 16 kHz WAV, up to 30 seconds:
.venv/bin/python keety.py transcribe /path/to/clip.wav

# Load the model, then record ten seconds from the default PipeWire microphone:
.venv/bin/python keety.py record --seconds 10
```

Wait for “Speak now” before speaking. Record mode requires `pw-record`, already
installed on this machine. Audio is recorded to a temporary directory and removed
when the command exits normally, errors, or is interrupted with Ctrl+C.
Transcription uses local model files with Hugging Face offline mode enabled;
the program has no audio upload code. Transcripts print to stdout, and timing
and Linux peak process RAM measurements print to stderr. Nothing is pasted into
another application automatically.

The CLI reloads the model on each invocation; the background runtime keeps it loaded.
INT8 can affect accuracy; test your own voice and technical terms.
This prototype limits clips to 30 seconds because longer inputs can consume
substantially more memory.

## Deterministic voice commands (0.2.0-dev)

### Grammar and intent explorer

Open **Keety Explorer** from the application launcher, run `keety-explorer`,
or run `./launch-explorer.sh` from this checkout. `python install_desktop.py`
installs both Keety and the separate explorer launcher.

The native GTK explorer has these views:

- **Grammar:** reusable patterns, their bindings, and every generated phrase.
- **Vocabulary:** canonical slot values, spoken forms, and rules using them.
- **Intents:** typed argument schemas and concrete structured meanings.
- **Try a command:** exact, learned-alias, and fuzzy parsing with candidate
  scores and rule evidence. Testing never executes actions or learns phrases.
- **History:** saved recordings/transcripts, playback, copying, and transcription retry.
- **Settings & phrases:** terminal-close preference and learned phrase removal.

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

**Command mode is permanent.**
Hold Super + R throughout one allowed phrase, then release.
The transcript and audio save first; a matching phrase then runs its fixed action.
Built-in phrases and learned aliases run immediately on an exact normalized match.
A sufficiently close match runs immediately and saves the heard phrase as an
alternate for that intent. Keety displays the matched command in its status;
there is no “Did you mean” prompt. Learned phrases can be removed with **Forget**.
Unrelated or ambiguous speech shows “Unrecognized command.” Audio and transcripts
remain saved for review. Retrying a saved transcript never executes or learns a command.

Stable intent IDs, display labels, and built-in phrases are generated into `INTENTS` in
[command_catalog.py](command_catalog.py), beside the fixed website URL registry.
`GRAMMAR` is generated from the same rules. Browse **Grammar** in Explorer for
built-in phrases, or **Settings & phrases** to review aliases and **Forget** a mistake.
Aliases persist in `~/.local/share/keety/aliases.json` (respecting `XDG_DATA_HOME`),
using a versioned JSON format and private file permissions. They stay outside Git.
This teaches the command matcher; it does not retrain the speech recognition model.
Starting another recording, retrying, or selecting history dismisses a pending suggestion.

| Allowed phrase | Action |
| --- | --- |
| move to other screen / move window to other screen | Move the window focused when recording started to the other screen |
| open a new terminal / open a terminal / open terminal / open new terminal | Open a fresh default terminal window on DP-1 |
| open chrome | Launch Chromium or focus an existing browser window |
| bring up chrome | Launch/focus Chromium and maximize with tabs visible |
| launch chrome | Same |
| focus chrome | Same |
| switch to chrome | Same |
| open chromium | Same |
| bring up chromium | Launch/focus Chromium and maximize with tabs visible |
| open google chrome | Same |
| bring up google chrome | Launch/focus Chromium and maximize with tabs visible |
| open gmail / bring up gmail | Bring up Gmail |
| open github / bring up github | Bring up GitHub |
| open x / open twitter / bring up x / bring up twitter | Launch X’s installed app or focus its existing window |
| maximize chrome / maximize chromium / maximize google chrome | Maximize the most recently used normal browser window |
| maximize discord | Maximize Discord’s app window |
| maximize x / maximize twitter | Maximize X/Twitter’s app window |
| close terminal / close the terminal / close a terminal | Close the most recently used terminal; ask if programs are running |
| close this terminal | Close the terminal focused when recording started; ask if programs are running |
| close discord | Close the most recently used Discord app window |
| close x / close twitter | Close the most recently used X/Twitter app window |
| close chrome / close chromium / close google chrome | Close one normal Chrome/Chromium window, including its tabs |
| open discord / bring up discord | Launch Discord if closed, otherwise focus its existing app window |
| show all windows / show all open windows / show all open window | Show a searchable window list across all screens and workspaces; select a window to focus it, or press Escape to dismiss |

Discord and X use their installed desktop launchers (the Omarchy web apps on
this machine). Opening moves their windows to DP-1 and makes them fullscreen.
X and Twitter are synonyms for one intent. Exact app classes identify their
windows; ordinary browser tabs titled Discord or X are not treated as app windows.

Maximize commands select one existing window, move it to DP-1 and focus it,
then set maximized mode for both the compositor and app. Normal browser controls
remain visible; this is different from fullscreen. Repeating the command keeps
it maximized. If the app is closed, Keety reports that instead of launching it.

“Move to other screen” and “move window to other screen” work for any captured
window, including Chromium. The window moves to the other screen's active
workspace and receives focus. With more than two screens, the destination is
the next connected monitor in monitor-ID order. It reports an error if only one
screen is available. Fuzzy matches keep the original captured window as their target. A closed or replaced window is never substituted.

Terminal close commands close an idle shell prompt directly. If a program or job
is running, they show a confirmation in the bar popup with the chosen window's title.
The target is captured when recording starts and remains fixed while the
confirmation is pending. “Close this terminal” does
nothing if the focused window was not a terminal. “Close terminal” chooses the
most recently used terminal across screens/workspaces. Only that window is closed.

**Confirm before closing a terminal with running programs** defaults on. Turn it off in Explorer’s **Settings & phrases** to skip
confirmation for terminal-close commands; the choice persists locally in
`~/.local/share/keety/settings.json` (respecting `XDG_DATA_HOME`). Fuzzy matches follow the same running-program warning setting. Keety inspects the terminal's process tree and foreground process group. A lone
interactive shell with no live child jobs is treated as idle; foreground commands,
background/stopped jobs, and directly launched apps count as running programs.
Unknown states (including shared terminal servers that cannot be resolved per
window) still ask. This detects processes, not unsaved work. Closing can stop them. Keety sends a normal close request and leaves
any additional terminal/app confirmation to you; it never force-kills them.
If the selected window disappears or is replaced before approval, Keety will not
close a different window.

Close commands send a normal window-close request to one matching window,
preferring the most recently used match across workspaces. They do not focus,
move, launch, or forcibly kill the app. If no match exists, Keety says so.
An app may ask you to confirm closing; Keety leaves that dialog for you.
Close commands work even without DP-1. “Close Chrome” closes the whole selected
browser window and its tabs; it excludes the separate Discord and X app windows.
Gmail/GitHub tab closing and arbitrary window-name closing are not included.

The explicit spellings “g mail” and “git hub” are accepted too.

Website commands now operate on **normal browser tabs**:

1. Find an HTTPS tab whose hostname exactly matches the registered site.
2. Reuse it without reloading. If there are duplicates, prefer the focused
   browser window, then the most recently accessed matching tab.
3. If no matching tab exists, create one in the focused normal browser window,
   or the most recently used normal window. Open a normal browser window if needed.
4. Activate the tab and maximize its browser on DP-1 with tabs and address bar visible.

Private windows, standalone app windows from the earlier implementation, and
extension-only control windows are excluded. Existing app windows are left intact.
Pending navigations count as matching tabs to avoid duplicates during page loads.
Both “open” and “bring up” currently follow these same rules.

Tab control uses the already installed Playwright extension (0.4.0) and the pinned
local Playwright MCP runtime from `codex-browser-tools` (0.0.80). Keety sends fixed
JavaScript to the extension's tabs API; no AI agent interprets or runs commands.
The local connection is stored at `~/.config/keety/browser-connection.json`, with
mode 0600, using the installed runtime's `command`, `args` (including `--extension`),
and `env`. The existing extension connection token remains outside this repo.
This machine is configured; other installations need their own extension connection.
Keety keeps a connection open after the first website command; an extension control
tab supports that connection. Closing Keety stops its connection process.
A connection failure reports an error rather than opening duplicate fallback tabs.

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

The voice popup belongs to the bar on the monitor focused when recording starts.
It occupies no workspace or tile. Voice actions retain their existing display
policies: controlled browser/app commands target **DP-1**, current-window maximize
stays on its current screen, and move-to-other-screen selects another monitor.

The old GTK-window rule in [config/hyprland-keety.lua](config/hyprland-keety.lua)
only applies to the development window; the runtime creates no such window.

## Model provenance

- Original model: [NVIDIA Parakeet TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)
- Community conversion: [istupakov/parakeet-tdt-0.6b-v3-onnx](https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx)
- Runtime: [onnx-asr](https://github.com/istupakov/onnx-asr), using ONNX Runtime CPU

The converted model is marked CC BY 4.0 by its publisher. Credit belongs to
NVIDIA for the original model and Ivan Stupakov for the conversion/runtime.
Weights are downloaded separately and are not committed to this repository.
Keety is an independent app, not an NVIDIA product.

See [the first local benchmark](docs/first-run.md) for hardware and measurements.

## Validation

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_browser_tabs.cjs
.venv/bin/python tests/learning_smoke.py
.venv/bin/python tests/explorer_smoke.py
.venv/bin/python tests/runtime_smoke.py
.venv/bin/python tests/bar_popup_smoke.py
.venv/bin/python tests/bar_mode_smoke.py
.venv/bin/python tests/terminal_confirmation_smoke.py
.venv/bin/python tests/terminal_activity_smoke.py
.venv/bin/python tests/window_close_smoke.py
.venv/bin/python tests/tile_windows_smoke.py
.venv/bin/python tests/window_close_smoke.py --maximize
.venv/bin/python tests/window_close_smoke.py --maximize-current
.venv/bin/python tests/window_close_smoke.py --maximize --move
# With the public sample downloaded as described in docs/first-run.md:
.venv/bin/python tests/gui_smoke.py local/jfk.wav
.venv/bin/python tests/gui_smoke.py local/jfk.wav --auto
```

With the real Keety app closed and the shortcut installed, `tests/gui_smoke.py`
also supports `--ptt` and `--ptt --super-first`. These use a test-only virtual
keyboard with a standard evdev keymap to exercise the compositor binding and
D-Bus action, checking transcription before the second key is released.
`tests/shortcut_smoke.py` verifies taps never latch recording, both Super keys, both release orders,
and a deliberately dropped release message without recording audio.
The helper is built in a temporary directory using `cc`, `wayland-scanner`,
`wayland-client`, and `xkbcommon`; these are test tools, not app dependencies.
Its vendored protocol is from wlroots' `virtual-keyboard-unstable-v1.xml`, with
its license retained. No input setting changes are needed.

The GUI smoke test opens a temporary test window and substitutes a prerecorded
sample for the microphone. It verifies amplitude activity during recording and
no live text, then exercises key release with the installed recorder's exit-code-1
behavior, automatic on-screen transcription, actual model inference,
WAV/transcript/metrics persistence, history reloading and returning to ready.
It never records the real microphone. The owner confirmed microphone recording
works. A real recording previously skipped transcription because this installed
`pw-record` returned 1 after a requested stop despite saving a valid WAV. The
app now accepts that requested-stop result and validates/transcribes the WAV;
the regression test covers this exact case. The owner subsequently confirmed
that the meter and automatic transcription work in the updated app.

Say **“maximize this window”** to maximize the window focused when recording starts,
on its current screen. Repeating the command keeps it maximized; browser tabs
and normal window controls stay visible.

Say **“tile open windows”** (or **“tile all windows”**) to arrange the windows
on the workspace focused when recording starts in equal-sized grid cells (four
windows form a 2 × 2 grid). It exits maximize/fullscreen and separates groups.
The adapter uses positioned floating windows to avoid inheriting old split ratios,
respects monitor scaling and the panel, and leaves spare cells empty for odd counts.
Run the command again after opening or closing windows to rearrange the grid.
Keety is excluded. Other workspaces stay as they are; repeating the command keeps
the windows tiled.

### Menu-bar runtime

`launch.sh` starts `runtime.py`, a windowless `Gio.Application` retaining the
existing application ID and push-to-talk D-Bus actions. The user-owned
`config/keety-bar` widget renders a passive attached popup. Runtime state lives
privately under `XDG_RUNTIME_DIR`, including transcript, intent, amplitude samples,
and a per-confirmation token. Stale or repeated confirmation tokens cannot act on
a later command. The widget detects a stopped/unresponsive runtime.

`install_bar.py` installs the widget under `~/.config/omarchy/plugins/greg.keety`,
updates the user shell layout, and installs a login launcher. Existing plugin
files and shell config are backed up. Packaged Omarchy files are unchanged.
Plugin changes normally reload automatically; `omarchy restart shell` can apply
a change if this shell version retains the previous component in its cache.
