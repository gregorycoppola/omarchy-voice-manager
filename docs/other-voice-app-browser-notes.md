# Browser and tab notes from other voice-app reviews

Reviewed 2026-09-21 against the shallow reference clones and commits recorded
in [`../../other-apps/sources.json`](../../other-apps/sources.json). This note
records product ideas only; no upstream code or dependencies were copied.

## What the other apps do

| Project | Browser approach | Tab handling | What Skipper can learn |
| --- | --- | --- | --- |
| Genesis | Treats “open Firefox” as launching an application. | None found. | Keep simple app launching separate from tab navigation. |
| omarchy-voice (OMA) | Uses a bounded, model-driven browser/research worker and screen/page-text tools. It deliberately opens web apps or a dedicated research **window**, because Hyprland cannot see a regular browser tab. | No semantic tab chooser found. | Preserve a verified target and stop if focus/geometry changes. Its window-first design is not a replacement for Chromium tab access. |
| Omarvis | Drives Chromium through `agent-browser`, with a snapshot/persistent/attached browser mode. | Its browser catalog includes `tab list`, `tab new`, `tab close [ref]`, and `tab t2` (switch by stable reference). It can also read an accessibility-tree snapshot. | Stable tab references and an explicit owned-browser boundary are useful concepts. Its cloud voice/model path, profile-copy model, and full browser automation are not needed for Skipper tab switching. |

## Recommendation for Skipper

Use the existing local Chromium extension connection, expanded only enough to
return a snapshot of normal tabs:

```text
tab id, window id, title, HTTPS host/path, active, pinned, audible, last-accessed
```

Tab titles and URLs are private browser metadata. Reading them must be an
explicit optional permission, never written to diagnostics, and excluded from
private/incognito and extension-control windows.

Build a deterministic tab resolver before considering an LLM:

1. `switch to <tab query>` obtains one fresh snapshot.
2. Classify well-known local facts from the URL, for example a GitHub pull
   request from `/pull/<number>`.
3. Score exact host/title words and these classifications. A match must have a
   clear lead; otherwise show a picker with short redacted-safe labels.
4. Revalidate the selected tab ID immediately before activation. Browser tab
   IDs are session-local, so they are references for one command only, not
   durable user identifiers.

Examples:

- “switch to the PR tab” selects the sole open GitHub pull request; with two,
  it asks which PR.
- “switch to the browser-routing PR” matches title words first, then asks on a
  tie.
- “list GitHub tabs” presents a picker rather than reading all tab titles aloud
  by default.

Suggested initial command set:

- `list tabs` / `list GitHub tabs`
- `switch to <tab query>`
- `next tab`, `previous tab`
- `close this tab` (confirm)
- `reopen closed tab`
- `mute this tab`

Tab groups, moving tabs to another window, and page accessibility controls are
separate later features. “Open GitHub” versus “open a new GitHub tab” is
already intentionally separate in Skipper.

## Why not an LLM first?

The job is selection from a small current list, not open-ended understanding.
Rules plus a picker make the outcome explainable and avoid sending tab titles
or URLs to a model. A local LLM could later turn very loose requests into a
candidate query, but it must never activate a tab without the same deterministic
match/clarification step.

## Sources inspected

- Genesis: `README.md`, `bin/intent`, and `bin/execute`.
- OMA: `src/omarchy_voice/browser.py` and `src/omarchy_voice/tools.py`.
- Omarvis: `README.md`, `docs/reference.md`, and `omarvis/catalog.py`.

The existing broader comparison remains in
[`../../other-apps/REVIEW.md`](../../other-apps/REVIEW.md).
