# Changelog

## Unreleased — 0.2.0-dev

- “Bring up Discord” / “open Discord” reuse the existing app window or launch
  the installed Discord desktop entry, then show it fullscreen on DP-1.

- Gmail and GitHub website commands: “open” / “bring up,” with explicit
  “g mail” and “git hub” transcription variants.
- Reuse matching Gmail/GitHub tabs; otherwise open a tab in the existing normal
  browser window. Activate its window fullscreen on DP-1.
- Central command/website registry and an expandable Accepted commands list.
- Deterministic exact-host tab selection through the installed local browser
  extension; duplicate matches prefer the focused window and most recent tab.
- Standalone site windows are no longer created; earlier app windows are left intact.

- Global Super/Command + R hold-to-talk: press records, release either key
  transcribes and runs an exact command match without focusing the app.
- Recording uses only hold-to-talk: hold Super + R throughout the phrase,
  release to save and transcribe. The existing 30-second limit remains.
- Removed the speech detector, its model/download manifest, continuous capture,
  utterance queue, and related UI and tests. Removed manual Record/Stop buttons.
- Command mode is permanent. Unlisted phrases trigger no action.

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
