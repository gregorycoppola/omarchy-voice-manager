# Keety

Current release: **0.1.0**. This checkout includes **0.2.0-dev** voice-command
work. See [the changelog](CHANGELOG.md).

A local speech-to-text app in development for an M2 MacBook Pro running ARM
Linux / Omarchy. It has a native GTK4 window with Record/Stop, a live microphone
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
.venv/bin/python speech_activity.py download
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

**Hands-free listening is on by default.** Speak an allowed command, then pause
for about 0.7 seconds. Keety detects speech, saves the take, transcribes it and
runs an exact grammar match, then continues listening. No Record/Stop clicks
are needed. The level display shows microphone amplitude and speech probability.

Press **Pause listening** to close the microphone stream. The app remains open.
Re-enable **Hands-free listening** to resume. Closing Keety stops listening;
this version does not install login autostart or an always-running system service.

For a manual take, pause hands-free mode, then press **Record**. The scrolling
bars show the actual microphone amplitude.
There is no live text preview. Press **Stop** and Keety automatically transcribes,
shows the final text, and saves it. A spinner indicates the brief transcription
step. The model is already loaded, so no new model load is needed after Stop.
Recordings stop automatically at 30 seconds. The model stays loaded until the
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

The CLI reloads the model on each invocation; the GUI keeps it loaded. A global
push-to-talk shortcut and longer-recording segmentation are future work.
INT8 can affect accuracy; test your own voice and technical terms.
This prototype limits clips to 30 seconds because longer inputs need segmentation
and can consume substantially more memory.

## Deterministic voice commands (0.2.0-dev)

Both **Voice commands** and **Hands-free listening** start enabled. Speak one
allowed phrase and pause, or use manual Record/Stop with hands-free mode paused.
The transcript and audio save first; a matching phrase then runs its fixed action.
The toggle defaults on each time the app starts. With it off, all recordings
are dictation. Retrying a saved transcript never executes a voice command.

The entire grammar is the explicit `GRAMMAR` table in [os_actions.py](os_actions.py):

| Allowed phrase | Action |
| --- | --- |
| open chrome | Launch Chromium or focus an existing browser window |
| bring up chrome | Launch/focus Chromium and enter fullscreen |
| launch chrome | Same |
| focus chrome | Same |
| switch to chrome | Same |
| open chromium | Same |
| bring up chromium | Launch/focus Chromium and enter fullscreen |
| open google chrome | Same |
| bring up google chrome | Launch/focus Chromium and enter fullscreen |

Matching only lowercases, collapses whitespace and removes surrounding
sentence-ending `. ! ?` punctuation. Extra words, negations and unlisted phrases
do not match. There is no fuzzy matching, LLM command interpretation, arbitrary
shell execution, or chaining. ASR can still mishear speech; matching itself is
deterministic. Only the fixed browser action is implemented.

### Speech detection and noise

Hands-free mode uses the [Silero VAD model](https://github.com/snakers4/silero-vad)
locally through ONNX Runtime, rather than an amplitude-only trigger. Its pinned
2.3 MB model and MIT license download separately using `vad-manifest.json`.
This is speech detection, not speaker identification or a wake-word system.

The current deterministic segmentation settings are in `speech_activity.py`:
96 ms of confident speech starts capture, with 320 ms of pre-roll to preserve
the beginning; 704 ms of low speech probability ends it. Takes with less than
256 ms of confident speech are discarded. Long utterances split at 28 seconds.
The speech-start probability threshold is 0.6; the end threshold is 0.35.
Thresholds may need tuning for a particular room, microphone or speaking style.

Background audio stays in a bounded memory buffer. Only completed detected-speech
segments are saved as recordings. A bounded queue permits continued listening
during transcription. Pause cancels not-yet-started command actions, while queued
audio can finish saving its transcript. An already-dispatched OS action is not
undone. Playback and manual recording are available after pausing hands-free mode.

Tests with generated hum/hiss produced no take before speech; the JFK fixture
triggered speech segments. The GTK hands-free test covers real VAD/ASR, automatic
endpoints, persistent text and audio, continued listening, and closing the capture
stream on Pause. These tests do not establish accuracy in every noise environment.

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
# With the public sample downloaded as described in docs/first-run.md:
.venv/bin/python tests/gui_smoke.py local/jfk.wav
.venv/bin/python tests/gui_smoke.py local/jfk.wav --auto
.venv/bin/python tests/handsfree_smoke.py local/jfk.wav
```

The GUI smoke test opens a temporary test window and substitutes a prerecorded
sample for the microphone. It verifies amplitude activity during recording and
no live text, then exercises Stop with the installed recorder's exit-code-1
behavior, automatic on-screen transcription, actual model inference,
WAV/transcript/metrics persistence, history reloading and returning to ready.
It never records the real microphone. The owner confirmed microphone recording
works. A real recording previously skipped transcription because this installed
`pw-record` returned 1 after a requested Stop despite saving a valid WAV. The
app now accepts that requested-stop result and validates/transcribes the WAV;
the regression test covers this exact case. The owner subsequently confirmed
that the meter and automatic transcription work in the updated app.
