# Changelog

## Unreleased — 0.2.0-dev

- Replace the everyday GTK voice window with a windowless runtime and an attached
  menu-bar popup. It shows microphone levels, recognized speech, and intent without
  joining the tiling layout or taking keyboard focus. Successful actions dismiss
  the popup immediately; the latest intent name stays to the left of Keety in the bar.
- Move recording history, playback/retry, terminal-close settings, and learned
  phrase removal into Explorer. Terminal-close confirmations appear in the bar
  popup and bind approval to a unique request and captured window.

- Add a separate native **Keety Explorer** app for browsing grammar rules,
  vocabulary, structured intent schemas/instances, and testing command parses
  with fuzzy candidate evidence. The explorer does not run actions or load speech.
- Generate accepted phrases from shared grammar patterns and typed vocabulary.
  Voice parsing now returns structured intents while retaining existing action
  IDs, learned aliases, and all previous phrases. Browser patterns apply to all
  Chrome/Chromium name variants; different slot values remain distinct fuzzy
  candidates.

- Keety now starts in the background with an Omarchy top-bar status button.
  Click for history/settings; closing the window hides it without stopping
  push-to-talk. An explicit Quit button stops Keety.

- Tiling now assigns equal-sized grid cells, including a 2 × 2 grid for four
  windows, instead of preserving the old unequal layout splits.

- “Tile open windows” restores the captured workspace’s windows to normal
  tiling, excluding Keety. Repeated commands keep the windows tiled.

- Close-enough, unambiguous voice matches now run and learn their phrase
  automatically without a recognition confirmation. Terminal running-job
  warnings still follow the saved preference.

- “Maximize this window” maximizes the window captured when recording starts
  on its current screen, including after fuzzy confirmation.

- “Move to other screen” / “move window to other screen” move the window focused
  when recording started to the other monitor's active workspace and follow it.
  Fuzzy confirmations retain that target rather than moving the confirmation UI.

- Idle terminal prompts close directly. Confirmation is needed only for running
  commands/jobs or an unknown process state, unless disabled in preferences.

- “Close terminal” selects the most recent terminal; “close this terminal” uses
  the window focused when recording started. Confirmation names that window
  and remains tied to it even after focus changes. A saved setting can disable
  exact-match terminal confirmations; fuzzy matches always require approval.

- “Open a new terminal” / “open a terminal” launch a fresh default terminal
  through Omarchy and focus it on DP-1.

- Browser and website commands preserve Chromium’s tabs/address bar by using
  maximized mode. Bringing up an already-fullscreen browser restores its controls.

- Super + R starts recording immediately and stops on release. No delay or
  tap-to-toggle mode; quick taps end without needing a second press.
- Raw R/Super release events stop capture regardless of focus/modifier changes.
- Held-key renewals and a 700 ms timeout stop capture if a release message is
  dropped or the shortcut configuration reloads. Late renewals cannot restart it.

- “Maximize Chrome/Chromium,” “maximize Discord,” and “maximize X/Twitter”
  select an existing window on DP-1 and set maximized mode, keeping normal
  app controls visible. Repeated commands keep the window maximized.

- Open/bring up X or Twitter reuses the installed X app window, or launches it.
- Close Discord, X/Twitter, or Chrome/Chromium sends a normal close request to
  one matching window. Open and close have separate learnable intent IDs.
- Incomplete single-word speech no longer produces a fuzzy command suggestion.

- Group built-in phrases under stable intent IDs and display labels.
- Close transcriptions open a prominent modal “Did you mean…?” dialog; Yes runs the fixed command and
  remembers a local alias. No dismisses it. Learned phrases persist across
  restarts and can be forgotten in the UI. No additional model or dependency.

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
- Command mode is permanent. Suggestions require confirmation before acting.

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
