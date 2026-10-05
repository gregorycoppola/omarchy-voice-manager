# Feature opportunities: Spotlight, Keystroke, and Skipper

Date: October 2, 2026.

Status: audio-device selection implementation started in the private checkout
after the implementation handoff.
Other feature areas below remain proposals for co-design.

## Goal

Expand Skipper's useful desktop operations while keeping the agreed interaction:
specific verb → meaningful argument → next argument only when needed.
Typing remains the default. Voice input and broader language interpretation are
later layers over the same explicit operations.

See [Picker verb semantics](picker-verb-semantics.md) for the agreed meanings of
Move, Close, Minimize, Maximize, Focus, Show, and Open.

## Reference features

These are documented upstream capabilities, not claims from local execution tests.

| Project | Relevant documented capabilities | Ideas to adapt |
| --- | --- | --- |
| Spotlight | Audio, Wi-Fi, Bluetooth, service, container, and port views; live toggles; file and clipboard search; reminders and calculations. | Show real device/state information inside argument lists. |
| Keystroke | Argument hints and Tab advancement; search into nested menus; browser profiles and recent projects; extensions; optional local semantic matching. | Explain the pending argument, support direct typed paths, and keep feature providers separate. |

Sources checked October 2, 2026:

- [Spotlight documentation](https://maajix.github.io/omarchy-spotlight/docs/)
- [Keystroke README and feature list](https://github.com/evindor/keystroke)

The menu examples and priorities below are Skipper proposals, not descriptions
of either project's interface. Upstream features do not automatically become
requirements for Skipper.

## Proposed order

1. Audio output and microphone selection: a small, useful feature that exercises
   a dynamic argument provider and supports eventual voice use.
2. Argument guidance throughout the picker: show what is selected and what is
   still required, including for existing window commands.
3. Files and recent projects: settle search scope and application choice first.
4. Other device controls and explicit state changes: Wi-Fi, Bluetooth, night light.
5. Broader utilities: clipboard, reminders, calculations, and developer system views.

Audio is the recommended first implementation, not a recorded user choice
between every item in this list. The broader backlog is for subsequent co-design.

## First implementation proposal: switch audio device

### Menu

```text
switch…
  audio output…
    Laptop speakers       Current
    USB headphones
    Monitor speakers
  microphone…
    Built-in microphone   Current
    USB microphone
  workspace…              Existing workspace-switch flow
```

Labels are examples. Populate devices from the local audio system; do not invent
device names or list disconnected hardware as executable choices. Duplicate names
need a useful subtitle such as connection/device description.

### Meaning

- `Switch audio output` selects the system's default playback device.
- `Switch microphone` selects the system's default capture device.
- A microphone choice does not start recording, load Voxtype, or enable voice mode.
- Choosing the current default is a successful no-op with an explanatory message.
- Default selection and moving an already-running application's stream are separate
  behaviors. Version one changes the default only. The UI must not promise every
  existing stream moved; actual routing also depends on the audio session manager.
- Volume, mute, audio profiles, and Bluetooth pairing are outside this first change.

### Interaction

1. Accept Switch, then audio output or microphone.
2. Load the relevant live device list asynchronously when that level is reached.
3. Filter locally while typing, using the existing text matching approach.
4. Tab accepts a device; Enter executes a complete selection. A unique branch
   may expand automatically, but a unique device never activates automatically.
5. Back returns to the preceding level without changing the default.
6. After execution, show the resulting default or explain why the change failed.

Keep the assembled command visible, for example:
`Switch audio output → USB headphones`.

### Dynamic state

- Show loading, empty, and unavailable states distinctly.
- Mark the current default using actual system state, not a remembered selection.
- Refresh on entry and when devices change, without blocking text entry.
- Preserve selection by device identity when the list refreshes, not by row number.
- Re-resolve the chosen device before execution. A removed device must not be
  replaced by the next list entry or another device that reused its numeric ID.
- Do not start a new global device scan on every keystroke.

### Implementation boundaries

- An audio provider returns device IDs, display labels, search forms, direction,
  current-default status, and availability. UI code does not parse command output.
- The runtime owns listing and execution. Inspect the installed Omarchy/audio
  integration before choosing its adapter; prefer structured local data and an
  existing supported control interface. Do not commit to parsing human-formatted
  status output in this design.
- The picker represents device selection as an explicit argument level alongside
  existing workspace and website providers.
- Execution passes a structured selection tied to its captured identity rather
  than recovering the intended device through fuzzy matching of its display name.
- Keep authored intent definitions in the private dataset where appropriate;
  discover live device choices in Skipper. No hard-coded personal hardware names.
- If sequence support is implemented, queue a complete device selection and
  revalidate it when that step runs. Otherwise explicitly disable Add step in
  this flow until supported; never silently omit it.

### Acceptance criteria for the implementation phase

- Switch offers audio output, microphone, and the existing workspace operation.
- Output and input devices appear only in their respective lists.
- The current default is identified correctly, including after a switch.
- Tab, Enter, Back, and cancellation retain their established meanings.
- Unplugging or replacing a selected device cannot switch to an unintended device.
- No-device and failed-backend cases remain usable and explain the problem.
- Selecting a microphone leaves voice recognition unloaded.
- Existing window, website, and workspace flows retain their behavior.

These are review criteria, not a report of tests performed. Test execution is a
separate step when requested.

## Follow-up designs

| Opportunity | Possible Skipper flow | Question to resolve |
| --- | --- | --- |
| Argument hints | Show the selected verb/target and the next required argument. | Breadcrumbs, a short prompt, or both? |
| Nested search | Type a full command while menus reveal its arguments. | How should ambiguous words spanning levels be displayed? |
| Files | Open → file → matching file. | Which directories and file types should be searched? |
| Recent projects | Open → project → project → editor or terminal. | Where do projects come from, and what does opening one create? |
| Clipboard | Copy → clipboard entry. | Copy only, or a distinct Paste action into the captured window? |
| State controls | Enable / Disable → night light, Wi-Fi, etc. | Which controls belong in the first release? |
| Reminders | Remind → message → time. | Which existing reminder service should own the reminder? |
| Developer views | List → ports / services / containers. | Read-only inspection first, or explicit follow-up actions? |
| Browser profiles | Open → website → browser/profile arguments. | At which stage should profile selection appear without adding mandatory steps? |

Prefer explicit Enable and Disable operations over a hidden-state toggle when
building sequences. This is a proposal to discuss before adding those verbs.
Retain deterministic text matching for now; a competitor's semantic model is not
part of this implementation scope.

## Handoff and editing ownership

The design is ready for the code editor to review. Once the live-checkout owner
releases it, read its current instructions, status, and newly pushed changes before
editing. Base implementation on that latest state, not this worktree's older code
snapshot. Carry over this document without overwriting newer design notes.

Do not deploy, restart, merge, or push from the design window while the other
window owns live changes. Private development and public publishing remain
separate; this proposal requests no public release.

## Audio implementation notes

- `audio_devices.py` reads structured `pactl` JSON from PipeWire's PulseAudio
  interface and changes only the default sink/source. No recording or ASR starts.
- Device IDs bind direction, node name, and PipeWire object serial. The runtime
  accepts a structured picker selection, revalidates its identity, and confirms
  the resulting default.
- Lists load asynchronously on entering the argument level and refresh every
  three seconds while it is open. A changed selection requires reselection.
- The current default and device description appear in the row subtitle.
- Omarchy's Asahi microphone mapping is recognized as an input, not an output.
  Ordinary speaker-monitor sources are excluded unless already the default.
- Add step is unavailable for audio selections in this iteration. Queued steps
  must be run before switching an audio device.
- No behavioral tests or default-device changes were performed by the agent.

## Filename search: first implementation

Implemented **Open → file → filename results** after user approval. The default
scope is the home directory, excluding hidden and ignored paths. This scope was
chosen as the initial default; there is not yet a folder-selection preference.

- `file_search.py` invokes `fd` without a shell; multiword queries match filename
  fragments in order, case-insensitively. Contents and directory names are not
  the search target.
- Entering Open → file loads recent files immediately, merging desktop XBEL
  visits/application access timestamps with Skipper opening requests. Typing filters
  it with a 180 ms debounce, including single-character queries. Superseded
  subprocesses are cancelled, results carry a request generation, and searches
  time out after five seconds.
- At most 80 candidates are returned, then ranked by the picker. This bounds work
  and is not a promise to find the globally best match for a broad query.
- Rows show the filename and parent folder. Selection submits an opaque ID from
  the current result set; the backend checks the captured file identity before
  asking `xdg-open` to open it. Status reports a request, not confirmation that
  an application successfully displayed the document.
- Tab accepts, Enter opens, and Back returns to the previous level. No automatic
  opening. File selections cannot yet be queued with Add step.
- Recent projects and editor selection remain a separate later feature.
- No behavioral tests or actual document-opening actions were run by the agent.

Recent-file rows preserve newest-first order when the query is empty; text
ranking applies only once a filename query is entered. Desktop history is read
only, and Skipper additions use a local SQLite database capped at 500 paths.
Neither source uses filesystem modification time to rank recent access.

## Explicit system controls: implementation

Implemented Enable/Disable for night light, Wi-Fi software radio, and individual
Bluetooth adapters, plus Connect/Disconnect for paired Bluetooth devices. The
provider lists state without changing it and reloads while its level is visible.

`system_controls.py` uses the installed Hyprsunset interface, NetworkManager's
`nmcli`, and BlueZ D-Bus. Commands request a concrete state and verify it rather
than invoking a toggle. Bluetooth identity is rechecked against its captured
adapter/device address. Unknown or unavailable controls stay non-executable.

Night light retains an existing enabled temperature when already enabled; a new
enable sets 4000 K and disable sets 6500 K, matching Omarchy's controls. It starts
the installed user Hyprsunset service only when enabling needs it. These changes
do not alter scheduled profiles. Wi-Fi controls affect the software radio; they
do not choose a network or bypass hardware blocks. Bluetooth pairing and scanning
are not included. Connecting headphones does not also select an audio default.

Requests use structured picker IDs. Device lists and states remain local. No
control was activated during development, and no behavioral tests were run.
Sequence integration remains deferred; Add step is unavailable in these levels.
