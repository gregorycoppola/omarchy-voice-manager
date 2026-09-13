# Changelog

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
