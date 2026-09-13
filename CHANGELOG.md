# Changelog

## Unreleased — 0.2.0-dev

- Gmail and GitHub website commands: “open” / “bring up,” with explicit
  “g mail” and “git hub” transcription variants.
- Reuse each site's dedicated Chromium window, fullscreen on DP-1; launch a
  site window if absent, using existing browser logins.
- Central command/website registry and an expandable Accepted commands list.
- Ordinary browser tabs are not searched; website windows are managed separately.

- Global Super/Command + R hold-to-talk: press records, release either key
  transcribes and runs an exact command match without focusing the app.
- Hands-free listening now defaults off; command mode is permanent.
- Unlisted phrases show “Unrecognized command” and trigger no action.
- Optional hands-free mode: local Silero VAD detects speech onset/end.
- Continuous amplitude/speech-probability display and explicit Pause listening.
- Background audio stays in a bounded buffer; detected utterances save and
  transcribe automatically, then pass through the exact grammar.
- About 0.7s silence endpoint, pre-roll, short-noise rejection and a 28s take limit.
- Pause prevents queued utterances from starting OS actions.

- Voice commands use an explicit phrase-to-action table.
- “Open Chrome” / “bring up Chrome” and listed aliases launch or focus Chromium.
- “Bring up” phrases also set fullscreen; repeating them keeps fullscreen enabled.
- Keety stays pinned on eDP-1; controlled browser windows move to external DP-1.
- Exact normalized matching; unmatched speech remains saved for review.
- Saved transcription retries never execute commands.

## 0.1.0 — 2026-09-13

First working release for the tested M2 ARM Linux / Omarchy installation.

- Native GTK4 window with Record and Stop.
- Microphone amplitude bars driven by captured PCM audio.
- Automatic transcription immediately after recording stops, with a progress spinner.
- Persistent WAV audio, text transcripts and timing metadata; reloadable history.
- Playback, Copy text, Open folder and manual transcription retry.
- Local Parakeet TDT 0.6B v3 INT8 inference; model stays loaded in the GUI.
- Verified requested-Stop handling for PipeWire's exit code 1.
- Per-user application launcher installer and CLI for short WAV files.

The owner confirmed recording, amplitude feedback and automatic transcription
work on the target machine. Automated tests cover audio bounds, meter levels,
the Stop regression, automatic recording end, visible text and saved history.

Measured on an 11-second speech sample: 0.417 seconds of CPU transcription,
0.833 seconds of model loading, and 1285.6 MiB peak process RSS.

Limitations: 30 seconds per take, default PipeWire microphone, tested on one
ARM Linux installation. No global shortcut, window-management integration or
long-recording segmentation yet. This is a source release; models and runtime
dependencies are downloaded separately. Recordings are never included.
