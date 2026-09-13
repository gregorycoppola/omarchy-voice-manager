# Keety

Current release: **0.1.0**. This checkout includes **0.2.0-dev** voice-command
work. See [the changelog](CHANGELOG.md).

A local speech-to-text app in development for an M2 MacBook Pro running ARM
Linux / Omarchy. It has a native GTK4 window with hold-to-talk recording, a live microphone
amplitude display, saved recordings,
transcript history, playback and Copy text, plus a command-line interface.

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

Launch **Keety** from the application launcher, run `keety` in a terminal on
this installation, or run `./launch.sh` from the checkout.

**Hold Super/Command + R to speak; release either key to transcribe.** Keety
must be open and ready, but another app can have keyboard focus. The amplitude
bars show recording activity; the completed transcript stays visible and an
exact command match runs automatically. Takes are limited to 30 seconds.
Pressing the chord starts recording immediately, with no hold threshold.
A quick tap makes only a short take; it never toggles recording on. Releasing R or Super stops the
recording immediately through a raw keyboard event, even if focus changes.
While held, the shortcut renews a short recording lease every 200 ms. If the
release message is lost or Hyprland reloads, recording stops within about 700 ms
of the last renewal. A late renewal cannot restart it. Wait for transcription to
finish before holding the shortcut for another take.

The shortcut is installed on this machine in `~/.config/hypr/keety-ptt.lua`,
loaded by `~/.config/hypr/bindings.lua`. Source:
[config/hyprland-keety-ptt.lua](config/hyprland-keety-ptt.lua).
The binding uses physical XKB codes for R (27) and left/right Super (133/134).
Changing the chord requires updating both the binding and its tracked keycodes
after checking for conflicts, then running `hyprctl reload` and `hyprctl configerrors`.
The shortcut is a separate Hyprland configuration; the desktop installer does
not install it. It sends typed D-Bus actions through `gapplication`.

The microphone records only while you hold Super + R, up to 30 seconds.
Release either key to stop, save the audio, transcribe it, and run an exact
command match. Pauses in your speech do not end the recording.
The scrolling bars show microphone amplitude. There is no live text preview.
A spinner indicates transcription; the model stays loaded until the
window closes. Audio (`.wav`),
transcripts (`.txt`), and timing metadata (`.json`) are saved in
`~/.local/share/keety/recordings/` (or under `XDG_DATA_HOME` when set).
The transcript stays visible and the history is restored when reopening Keety.
Use **Play recording**, **Copy text**, **Transcribe again**, or **Open folder**.
The GUI retains audio even if transcription fails, so it can be retried.
Closing during a take stops and finishes saving it; close again afterward.
There is no automatic deletion; files remain until you delete them from the folder.

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

The CLI reloads the model on each invocation; the GUI keeps it loaded.
INT8 can affect accuracy; test your own voice and technical terms.
This prototype limits clips to 30 seconds because longer inputs can consume
substantially more memory.

## Deterministic voice commands (0.2.0-dev)

**Command mode is permanent.**
Hold Super + R throughout one allowed phrase, then release.
The transcript and audio save first; a matching phrase then runs its fixed action.
Built-in phrases and learned aliases run immediately on an exact normalized match.
A close match opens a prominent modal **Did you mean…?** dialog with
**Yes — run and remember** and **No**, bringing Keety forward. Escape or closing
the dialog dismisses it too.
Yes saves the heard phrase as an alias for that intent and runs the command.
Next time that phrase is recognized, it works immediately. No dismisses the
suggestion without saving or running anything. Unrelated or ambiguous speech
shows “Unrecognized command.” Audio and transcripts remain saved for review.
Retrying a saved transcript never executes a command or offers a suggestion.

Stable intent IDs, display labels, and built-in phrases live in `INTENTS` in
[command_catalog.py](command_catalog.py), beside the fixed website URL registry.
`GRAMMAR` is derived from those phrases. Expand **Accepted commands** for built-in
phrases, or **Learned phrases** to review your aliases and **Forget** a mistake.
Aliases persist in `~/.local/share/keety/aliases.json` (respecting `XDG_DATA_HOME`),
using a versioned JSON format and private file permissions. They stay outside Git.
This teaches the command matcher; it does not retrain the speech recognition model.
Starting another recording, retrying, or selecting history dismisses a pending suggestion.

| Allowed phrase | Action |
| --- | --- |
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

To add a website, add its fixed HTTPS URL and exact hostname to `SITES`, then
add its `site:<key>` intent and accepted phrases to `INTENTS`. No wildcard domain command
is enabled. Tab-selection rules live in `browser_tabs.js`, using the documented
[Chrome tabs](https://developer.chrome.com/docs/extensions/reference/api/tabs)
and [windows](https://developer.chrome.com/docs/extensions/reference/api/windows) APIs.

Exact matching lowercases, collapses whitespace and removes surrounding
sentence-ending `. ! ?` punctuation. Fuzzy suggestions use Python's standard
library text similarity, scoring built-in and learned phrases and grouping them
by intent. A suggestion needs at least 0.72 similarity and a 0.06 lead over the
next intent; ambiguous matches, explicit negation, single-word fragments, and long dictation are skipped.
These are initial heuristics, not confidence probabilities; some mishearings may
still produce no suggestion. Fuzzy matches always require a click before acting.
No extra model or dependency is needed. Website destinations and OS actions remain
fixed; speech cannot supply a URL, shell command, or browser argument.

The OS adapter reads Hyprland's window list, focuses an exact browser class, or
launches the installed browser desktop entry. It excludes Chromium-hosted web
apps such as Discord. On this installation, “Chrome” maps to Chromium.

### Two-screen layout on this MacBook

Keety opens as a pinned floating window on the laptop panel, **eDP-1**. It stays
visible across that screen's workspaces. Its voice commands move the controlled
browser to the active workspace on the external screen, **DP-1**, before focusing
or fullscreening it. If DP-1 is absent, commands report that it is disconnected.
They do not redirect controlled apps onto the laptop panel.

The installed user rule is `~/.config/hypr/keety.lua`, loaded by
`~/.config/hypr/hyprland.lua`. Its source is [config/hyprland-keety.lua](config/hyprland-keety.lua).
Display names are deliberately specific to this machine. This rule does not
change the experimental display driver or monitor modes.

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
.venv/bin/python tests/window_close_smoke.py
.venv/bin/python tests/window_close_smoke.py --maximize
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
