# Skipper

Skipper is a language-controlled desktop tool for **Omarchy Quattro**. Type a
command or hold a shortcut to speak, then focus, open, move, or tile windows.
It combines a local speech recognizer, a local intent grammar, and optional
OpenAI help for unfamiliar wording.

**Working prototype · version 0.3.2 · independent community plugin.**
This is not an official Omarchy project or a catalog endorsement. You can install
it directly from this repository. Tested on Linux aarch64; x86_64 has not yet
been validated. Requires Omarchy's Lua Hyprland API and Quickshell.

## Install with an AI assistant

If you use an LLM coding assistant with terminal access on your Omarchy machine,
you can give it this prompt. You can also read the code without installing anything.

```text
Help me install Skipper from:
https://github.com/gregorycoppola/omarchy-voice-manager

Read its current README and docs/first-run.md, then check my Omarchy version,
CPU architecture, system dependencies, and any existing Skipper installation.
It requires Omarchy Quattro's Lua Hyprland API and Quickshell; aarch64 is the
tested platform. Tell me if my system is incompatible or untested.

Use the documented Omarchy plugin installation and plugin_setup.py commands.
Set up local voice input, reusing a compatible model if available. Explain
the approximately 670 MB model download, shortcut changes, and optional
autostart before applying them. Preserve my other bindings and existing data;
do not use --replace-existing without reviewing the conflicting files with me.

Leave OpenAI fallback off unless I request it. If I enable it, let me enter
my key privately through plugin_setup.py cloud; never ask me to paste it here.

Run plugin_setup.py doctor and check Hyprland for configuration errors.
Start Skipper, then guide me through a hold-Super+R / release-to-parse test
and a typed command. Keep the separate debugger off. Report what worked,
what remains untested, and how to stop or uninstall it.
```

## Install

Run these commands in a terminal on Omarchy:

```bash
omarchy plugin add https://github.com/gregorycoppola/omarchy-voice-manager.git --enable
cd ~/.config/omarchy/plugins/greg.skipper
python plugin_setup.py install --voice --download-model --shortcut --autostart
~/.local/bin/skipper
```

The setup command installs pinned speech dependencies into a private Python
virtual environment and downloads the INT8 Parakeet model from Hugging Face.
The model download is approximately 670 MB; allow additional space for dependencies. The model is
loaded once during setup to check that it works on your machine.

System requirements: `python`, `gtk4`, `python-gobject`, `python-cairo`,
`hyprctl`, `gapplication`, and PipeWire's `pw-record`. If setup reports missing
packages, install them through `omarchy pkg add`, then rerun setup.
Omarchy does not run repository setup hooks automatically.

**Shortcut changes:** this voice preset replaces **Super + R** with hold-to-record
and **Super + Space** with Skipper's typed picker (normally Omarchy's launcher).
Omit `--shortcut` to manage bindings yourself; the preset is
[config/hyprland-skipper-voice.lua](config/hyprland-skipper-voice.lua).
`--autostart` starts Skipper at login. Setup backs up changed files and refuses
conflicting unowned Skipper launchers; `--replace-existing` explicitly backs up
and replaces those conflicts.

Already have a compatible model? Replace `--download-model` with
`--model-dir /absolute/path/to/parakeet-tdt-0.6b-v3-int8`. Model files and local
settings stay outside the plugin checkout and survive updates.

### Typed commands only

No speech model, microphone, or OpenAI account is required for the typed picker:

```bash
python plugin_setup.py install --shortcut --autostart
~/.local/bin/skipper
```

This preset uses **Super + R** for the typed picker. Without `--shortcut`, open
it through the bar widget. Voice dependencies are installed only with `--voice`.

## Try it

With the voice preset installed:

1. **Hold Super + R** while speaking. The top dropdown shows **● Recording…**.
2. **Release either key** to close the microphone and start transcription.
3. The dropdown shows the transcript in **green**, then the interpreted action
   in **white**. Supported commands execute; existing confirmations still apply.
4. If a focus request matches several windows, choose the intended window in
   the dropdown. No separate debugger window opens.

Examples:

- “Open Chromium in workspace three and tile it.”
- “Focus on the terminal.” (Choose a terminal if several are open.)
- “Focus on Chromium.”
- “Tile all terminals.”
- “Switch to workspace two.”

Use the installed application's actual name if Chromium is not installed.
Speech uses a bounded grammar; arbitrary multi-action sentences are not all
supported. The typed picker supports explicit sequences using **Add step**.

For typed commands, open **Super + Space**, type to filter choices, use **Tab**
to select arguments and **Enter** to run. **Shift + Tab** goes back. The picker
also supports selecting two windows by their displayed names and tiling them.

## Optional OpenAI fallback

Local speech recognition and grammar parsing run without an account or a charge
per command. Cloud fallback is **off on a new installation**. To enable it:

```bash
python plugin_setup.py cloud
```

This prompts for an API key without displaying it, saves it locally with private
permissions, and enables fallback. API usage is billed by your provider.
`OPENAI_API_KEY` in the runtime environment is also supported, but must be paired
with enabling fallback:

```bash
gapplication action io.github.gregorycoppola.Skipper voice-cloud "'on'"
# Disable it again:
gapplication action io.github.gregorycoppola.Skipper voice-cloud "'off'"
```

For unmatched nonempty speech, OpenAI receives the **transcript and relevant
local grammar/desktop vocabulary**, which can include window titles. Audio stays
local. Returned wording must validate against supported local actions before
execution. Suspected mishearings and unresolved meanings do not execute
automatically. Cloud responses are not automatically saved as learned rules.

## Check, update, or remove

```bash
# Check dependencies, model files, and credential availability:
python plugin_setup.py doctor

# Update a normal Git-installed plugin:
omarchy plugin update greg.skipper
python plugin_setup.py install --voice --shortcut --autostart

# Restart after updating:
gapplication action io.github.gregorycoppola.Skipper quit
~/.local/bin/skipper
```

To remove desktop integration and the widget:

```bash
python plugin_setup.py uninstall
omarchy plugin remove greg.skipper
```

Uninstall preserves recordings, history, settings, downloaded models, and the
Python environment. Modified integration files are retained for manual review.

## Limitations and debugging

- This release needs testing on more machines; aarch64 is the tested platform.
- Recognition can miss short or noisy recordings. Wait for readiness, hold the
  shortcut throughout the phrase, and inspect the displayed transcript.
- Empty recordings, unsupported actions, and unresolved interpretations execute
  nothing. Cloud errors are displayed and logged locally.
- Browser-tab control requires a separately configured Playwright browser
  connection. Core window control does not require that integration.
- Debug mode is off by default. For explicit preview-only debugging, stop the
  background voice service and launch the debugger:

```bash
gapplication action io.github.gregorycoppola.Skipper.VoicePreview quit
./launch-voice-preview.sh --debug --speech
```

Close the debugger and run `./launch-voice-preview.sh` to return to normal voice
mode. The **Skipper Explorer** application provides command inspection and history.

## Local data and documentation

Recordings and speech history live under `~/.local/state/skipper`; personal
settings, learned rules, and the Python environment under `~/.local/share/skipper`;
model configuration and an optional API key under `~/.config/skipper`. XDG directory
overrides are respected. These files can contain personal information and are
not part of the repository. See [data ownership](docs/data-ownership.md).

- [First run and troubleshooting](docs/first-run.md)
- [Command matching](docs/command-matching-notes.md)
- [Argument picker](docs/argument-picker-design.md)
- [Browser routing](docs/browser-site-routing.md)
- [Bundled intent definitions](docs/intent-dataset-integration.md)

The application and its intent definitions ship together; no second repository
is needed. Development checks use `python -B -m unittest discover -s tests` and
`node tests/test_command_levels.cjs`.

## License

Copyright (C) 2026 Greg Coppola. Skipper is licensed under **GNU GPL version 3
only**, without warranty. See [LICENSE](LICENSE) and
[third-party notices](THIRD_PARTY_NOTICES.md).

The optional model download is an ONNX conversion of NVIDIA Parakeet TDT 0.6B v3,
provided by [istupakov on Hugging Face](https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx)
under CC BY 4.0. Model weights are downloaded separately and are not bundled in
this repository.
