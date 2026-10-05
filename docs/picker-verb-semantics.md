# Picker verbs and window command levels

Design decisions, October 2, 2026.

Status: implemented on October 2, 2026.

## Precise verbs in the on-screen picker

The first level is a set of specific command verbs. Each verb has a distinct
meaning. Selecting a verb determines the operation; later levels supply its
arguments. Do not split command wording mechanically into one level per word.

| Verb | Intended meaning | Next choices |
| --- | --- | --- |
| Move | Relocate an existing window to a selected workspace or monitor. | Window, then destination. |
| Close | Request that an existing window close. This targets a window, not every window belonging to its app. | Window. |
| Minimize | Hide an existing window while keeping it open. | Window. |
| Maximize | Maximize an existing window. | Window. |
| Focus | Take the user to an existing window: switch to its workspace and give it keyboard focus, leaving the window where it is. | Window. |
| Show | Bring an existing window to the user's current workspace, restore it if minimized, and give it keyboard focus. | Window. |
| Open | Launch an app or open something new, such as a website or a new window. | Choices appropriate to what is being opened; detailed hierarchy still to be decided. |

Focus and Show deliberately have different meanings: **go to it** versus
**bring it here**. Neither means launching another instance of the application.
Open is separate from operations on existing windows. Launching an application
may reuse an existing window depending on the app; a guaranteed new window must
be represented explicitly where supported.

Example: Discord is on workspace 4, and the user is on workspace 2.

- Focus Discord: visit workspace 4 and focus that Discord window.
- Show Discord: bring that Discord window to workspace 2 and focus it.
- Move Discord → Workspace 3: relocate it to workspace 3. Whether the user
  follows the moved window remains an open design question.
- Open Discord: launch the application, subject to its launch behavior.

## Existing-window selection

Close, Minimize, Maximize, Focus, Show, and Move use a consistent window-selection
structure. Show includes minimized windows as well as visible ones.

After the verb, list individual windows together, with `this window` first.
Multiple windows belonging to one app remain individual entries in this list;
there is no required app-group level. Use short titles to distinguish them.

```text
move
  this window
  Discord
  Chrome — Documentation
  Chrome — Email
```

An entry such as Discord identifies one existing window. It is not an implicit
instruction to operate on all Discord windows. Further rules for filtering
inapplicable targets or displaying duplicate titles remain to be decided.

For Close, Minimize, Maximize, Focus, and Show, choosing the target completes the
arguments. Move continues to a destination level. Completing arguments does not
automatically execute the action.

## Move: verb → what → where

Only show destinations after the user has selected what to move. Workspaces and
monitors belong in the same destination list, without an intermediate
`Workspace…` / `Monitor…` category choice.

```text
move → Chrome — Documentation
  Workspace 1
  Workspace 2
  Laptop monitor
  External monitor
```

These labels are illustrative; actual choices come from available destinations.
This structure avoids enumerating every window × destination combination in the
initial menu.

## Selection and execution

Retain the agreed picker controls:

- One matching branch automatically reveals its next level.
- With multiple choices, Tab accepts the highlighted choice, defaulting to the top.
- Enter continues a branch or executes a completed command.
- Tab on a completed choice accepts it without executing it.
- Back / Shift+Tab returns to the previous level.
- Keep the assembled command visible so its operation and target are clear.

## Spoken language later

For now, picker verbs have explicit meanings. In particular, do not treat Focus,
Show, and Open as interchangeable operations in the menu.

Future voice input may accept a broader range of phrases, synonyms, or ambiguous
wording. That is a separate interpretation layer which should resolve to these
same specific intents. No policy for resolving ambiguity has been agreed yet;
do not implement silent guesses as part of this decision. Clarification or a
choice among interpretations remains a possibility for later design work.

## Remaining design questions

- Focus on a minimized window: restore it where it was, or offer another behavior?
- Maximize: exact relationship to tiling, fullscreen, and available monitor space.
- Move: whether to follow the window; which workspace receives it when selecting
  a monitor; whether destination choices include new workspaces.
- Multi-monitor Show: precisely which workspace counts as the user's current one.
- Which targets each operation excludes, and how unavailable choices are shown.
- Open: app launching versus explicitly creating another window, and its menu levels.
- Whether Hide remains a visible verb, and if so how it differs from Minimize.
- Other command families (Tile, List, recording, media, system commands) need
  their own agreed meanings and levels; earlier suggestions are not decisions.

## Relationship to existing notes

[Argument picker design](argument-picker-design.md) records the earlier
implementation. This decision document supersedes its Move destination grouping
and establishes the desired distinction between Focus, Show, and Open. It does
not change executable code, the shared dataset, or the installed plugin.

## Implementation choices for this iteration

- `picker_windows.py` supplies explicit window targets and exact executable wording.
  Core picker verbs do not fall back to a fuzzy execution guess when a target
  disappears or the arguments are incomplete.
- Move lists workspaces 1–10 plus other occupied positive workspaces; additional
  positive workspace numbers can be typed. Monitor labels include connector names.
- A monitor destination means its captured active workspace. If that destination
  changes before execution, the command asks the user to choose again. Move does
  not follow the relocated window.
- Focus restores a Skipper-minimized window to its original workspace. Show moves
  it to the workspace captured when the command picker opened and then focuses it.
- Maximize retains the existing window maximization behavior.
- Close retains terminal-job confirmation and rechecks the captured window identity.
- Open retains the existing app and website flows. Hide remains a legacy family;
  broader vocabulary cleanup is outside this iteration.
- Existing automated tests have not been run or updated for these changes.
