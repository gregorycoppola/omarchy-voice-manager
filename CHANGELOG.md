# Changelog

## 0.3.2 — 2026-10-08

- Package voice setup, pinned model download/reuse, health checks, and private API-key configuration.
- Support generic terminal focus with dropdown disambiguation and validate cloud window choices.
- Replace the long development README with installation and usage instructions.

- Add opt-in OpenAI fallback to normal voice input and dropdown choices for ambiguous window names.

- Add browser-tab selection and workspace-scoped tiling.
- Add local voice execution with top-dropdown feedback; keep the separate parser debugger opt-in.
- Make OpenAI fallback opt-in and use the installed runtime environment for the speech preview and worker.
- Document optional speech dependencies and model setup.

- Maintain intent definitions and their loader alongside the app; remove the separate repository synchronization step.
- Limit public snapshots to reviewed documentation and check archives for private data.

## 0.3.1 — 2026-10-05

- Offer installed, launchable apps by name, with an alias for the configured terminal.
- Add optional workspace and tiling arguments; Enter runs with the current defaults.
- Bring newly opened windows to the front after placement or tiling.
- Put all windows, all terminals, and all browsers first in Tile and List.
- Add selection of two named windows with identity checks and explicit tiling behavior.
- Refresh public dataset provenance and validate the release snapshots for personal data.

## 0.3.0 — 2026-10-02

- Bundle the compatible intent catalog so installation uses one GitHub repository.
- Make typing the default and remove custom speech recognition dependencies.
- Add staged verb and argument menus, full-path matching, and explicit window targets.
- Distinguish Focus (go to a window) from Show (bring it to this workspace).
- Add browser-history website choices and new/existing browser destinations.
- Add local filename search and recently opened files.
- Add audio-device defaults and explicit night light, Wi-Fi, and Bluetooth controls.
- Keep personal history in local storage outside the source repository.

### Earlier changes included in this release

- Name shell-style terminals using “shell” plus their path, omitting the hostname.

- Add show Chrome/Chromium, X/Twitter, and browser commands to restore hidden
  windows to their original workspace and focus them.

- Add hide Chrome/Chromium, X/Twitter, and browser commands with window selection.
- Rank displayed wording and action-word matches above alias-only matches.

- Use Tab to build numbered command sequences and Enter to run them in order,
  with fresh context between steps and pauses for confirmation or window choice.

- Refresh dynamic terminal suggestions while the box is open and hide stale
  named-terminal history entries without deleting saved history.
- Center terminal-close confirmation with Yes/No buttons, Enter/Y and Escape/N,
  plus token-bound spoken answers when voice is enabled.

- Keep suggested command wording stable while matching aliases; unmatched history
  entries no longer hide suggestions that match through another phrase.

- Add a third dropdown source: dynamic per-terminal commands generated from
  captured live names and shared templates, refreshed whenever the box opens.

- Add “list the terminals” with titles, workspaces, unique spoken names, and
  click-to-focus with window identity checks.

- Show dataset command suggestions alongside recent commands in the typing box;
  search unused supported phrases without creating fake history.

- Add exact “close all terminals” across workspaces, with captured targets,
  identity checks, and one batch confirmation for running or unknown jobs.
  Requires the matching development intent dataset.

## 0.2.0 — 2026-09-24

- Load shared intents and grammar from the public Omarchy Voice Dataset. Fresh
  installations fetch a pinned dataset snapshot; development can use a sibling
  checkout or an explicit dataset path.
- Store personal aliases, corrections, named actions, settings, and command
  history in owner-only local SQLite outside Git. Import legacy preferences once
  and preserve their original files as private backups.
- Add live fuzzy command history to Shift+Super+R: show the ten most recent
  distinct commands when empty and update matches while typing.
- Document shared versus personal data ownership and command matching precedence.


- Discover visible installed desktop applications as exact `open`/`launch`
  commands. Add an Explorer page listing the safe, unambiguous app vocabulary.

- Add exact volume, explicit mute/unmute, captured-display brightness, and media
  playback commands to speech and typed input. Report unsupported media actions.
- Add Explorer's Named actions editor for custom exact phrases mapped to existing
  typed commands, preserving window selection and terminal-close confirmation.

- Add centered typed commands, window selection for pair tiling and app closing,
  and correction handling for unknown commands. Restore the tiled workspace with
  show-all commands and improve equal-size grid layouts.
- Add browser opening in true fullscreen or tiled beside the originally focused
  window, with Chromium launch when needed and common browser typo handling.

- Rename the app and bar plugin to Skipper. Add a root Omarchy plugin manifest,
  portable widget defaults, explicit runtime setup/removal, and single-monitor
  support. Runtime dependencies and speech-model downloads live outside plugin
  checkouts. Marketplace submission awaits owner review.

- License Skipper's original code under GPL-3.0-only and document the separate
  licenses of the bundled test protocol and downloaded speech model.

- Add exact-only hide commands for terminals, non-terminal apps, and the current
  window. Restore the original workspace when tiling from a revealed hidden window.

- Add terminal, browser, and non-terminal app tiling views. Restore hidden
  windows with “tile all windows”; restrict “tile all apps” to exact matching.

- Launch desktop apps without capturing inherited output pipes. Confirm success
  from the app window appearing, preventing false launcher timeouts after Chrome,
  Discord, or X has already opened.

- Accept “focus on <window>” and “focus on the <window>” across live terminal names.

- Arrange the destination workspace after moving a window: maximize a lone
  window, or retile all destination windows into the equal grid. Maximize app
  commands now stay on the target's current screen. Add named-terminal maximize
  and accept “other window” as a screen synonym in named move commands.

- Add “move <window/app> to the other screen/monitor” for live terminal names
  and Chrome, Discord, X/Twitter. Support short task prefixes such as “explain
  terminal.” Preserve captured identity, reject duplicate/unknown names, and
  score fuzzy slot names separately from surrounding words.

- Add shared “focus” and “switch to” patterns for Discord and X/Twitter,
  reusing the existing app window and maximizing it at the front, or launching
  it when closed, consistently with Chrome. Named terminal focus also explicitly
  raises the selected window above overlapping windows, preserving its size.

- Unify open/bring-up and maximize presentation: float, maximize, explicitly
  raise, then focus the selected window. This applies to browsers, web apps,
  and new terminals, preventing windows from opening behind the floating grid.

- Add `close <window>` using the live terminal vocabulary, including fuzzy task
  names such as “close the patch monitor terminal.” Preserve running-program
  confirmations and captured-window identity; reject unknown/ambiguous names
  without falling back to the most recent terminal or learning ephemeral aliases.

- Inject live terminal names into reusable focus/switch/go-to grammar rules.
  Task/project names and fuzzy variants resolve to captured window identities;
  duplicate names remain ambiguous and closed/replaced windows are rejected.
  Explorer adds a Live windows vocabulary view and live command previews.

- Replace the everyday GTK voice window with a windowless runtime and an attached
  menu-bar popup. It shows microphone levels, recognized speech, and intent without
  joining the tiling layout or taking keyboard focus. Successful actions dismiss
  the popup immediately; the latest intent name stays to the left of Skipper in the bar.
- Move recording history, playback/retry, terminal-close settings, and learned
  phrase removal into Explorer. Terminal-close confirmations appear in the bar
  popup and bind approval to a unique request and captured window.

- Add a separate native **Skipper Explorer** app for browsing grammar rules,
  vocabulary, structured intent schemas/instances, and testing command parses
  with fuzzy candidate evidence. The explorer does not run actions or load speech.
- Generate accepted phrases from shared grammar patterns and typed vocabulary.
  Voice parsing now returns structured intents while retaining existing action
  IDs, learned aliases, and all previous phrases. Browser patterns apply to all
  Chrome/Chromium name variants; different slot values remain distinct fuzzy
  candidates.

- Skipper now starts in the background with an Omarchy top-bar status button.
  Click for history/settings; closing the window hides it without stopping
  push-to-talk. An explicit Quit button stops Skipper.

- Tiling now assigns equal-sized grid cells, including a 2 × 2 grid for four
  windows, instead of preserving the old unequal layout splits.

- “Tile open windows” restores the captured workspace’s windows to normal
  tiling, excluding Skipper. Repeated commands keep the windows tiled.

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
- Skipper stays pinned on eDP-1; controlled browser windows move to external DP-1.
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
