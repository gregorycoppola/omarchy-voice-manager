# First run

Follow the [README installation steps](../README.md#install) first. Install from
the Git URL; catalog membership is not required. This is an independent Omarchy
Quattro plugin and a working prototype.

## Start and speak

Run `~/.local/bin/skipper`, or click **Start Skipper** in the bar. With voice
setup complete, the speech model loads in the background. Hold **Super + R**
through a complete phrase, then release either key. Recording ends immediately;
transcription and parsing then start. The top dropdown displays the result.
The microphone is closed between recordings. The voice preset gives the typed
picker **Super + Space**. The typed-only preset instead uses **Super + R**.

Try “open Chromium in workspace three and tile it” or “focus on the terminal”.
Use the real installed app name. If multiple terminals match, choose one in the
dropdown. You can always use the typed picker to select visible actions and
arguments or compose a sequence using **Add step**.

## Optional local speech setup

From the plugin directory:

```sh
python plugin_setup.py install --voice --download-model --shortcut --autostart
```

This installs the pinned dependencies in the external environment, downloads the
pinned INT8 model, validates it, and installs the hold/release bindings.
To reuse a compatible model, replace `--download-model` with `--model-dir /path/to/model`.
Runtime does not download models. `SKIPPER_PARAKEET_MODEL` overrides the saved
model location. The older Voxtype model directory is a fallback for existing
users. This release has been exercised on Linux aarch64.

## Troubleshooting

Run `python plugin_setup.py doctor` from the plugin directory. It checks the
installed environment, GTK, local speech libraries, model files, capture command,
and whether an optional API key is available. It never prints the key. A nonzero
exit means at least one component of the full voice installation is missing;
typed-only users do not need the speech components.

- **No bar widget:** enable `greg.skipper` in Omarchy's plugin/bar settings.
- **No keyboard response:** ensure the runtime is running and the intended
  shortcut preset is loaded. Run `hyprctl configerrors` after changing bindings.
- **Speech loading:** wait for the model, then hold the shortcut again. An early
  press does not start a recording later without another press.
- **No speech heard:** check your default PipeWire input and hold the keys for
  the whole phrase. Audio is captured only during the hold.
- **Several matching windows:** select a title in the dropdown.
- **Unsupported wording:** rephrase or enable optional cloud help.
- **Changed packages after an OS update:** rerun setup with `--voice`.

## Optional OpenAI fallback

Run `python plugin_setup.py cloud` to enter an API key privately and enable
fallback. New installations leave it off. Unmatched nonempty text and relevant
desktop vocabulary may be sent to OpenAI; audio stays local. Validated literal
interpretations execute through the usual runtime, while uncertain meanings
request clarification. Fallback does not automatically learn a phrase.

Disable fallback with:

```sh
gapplication action io.github.gregorycoppola.Skipper voice-cloud "'off'"
```

See [data ownership](data-ownership.md) for local records, cloud audit logs, and
learned-rule storage. Keep personal data out of Git and shared reports.

## Preview-only debugger

Debug mode is opt-in. Stop the background voice service before launching it:

```sh
gapplication action io.github.gregorycoppola.Skipper.VoicePreview quit
./launch-voice-preview.sh --debug --speech
```

The debugger never executes commands. Its own OpenAI checkbox starts off and is
separate from the normal-mode cloud preference. Close it and launch
`./launch-voice-preview.sh` without `--debug` to resume normal voice mode.
