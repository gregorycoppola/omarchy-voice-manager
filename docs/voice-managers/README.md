# Omarchy voice manager field notes

The page includes the latency/accuracy/cost research framing and a proposed
model-adaptation track. See [research-plan.md](research-plan.md) for experiment
scope, measurement definitions, and the distinction between estimates and results.

Open `index.html` directly in a browser, keeping `cost-model.js` beside it. This is a static page:
no package installation, build step, fonts, analytics, or external scripts.
Search and filtering enhance the page; all notes remain readable without JavaScript.
The interactive cost calculator uses the adjacent local script. Its formulas,
rate snapshot, and defaults are in [cost-model.md](cost-model.md).

For a local HTTP preview with working links to Skipper source files, run from
the private repository root:

```sh
python -m http.server 8765 --bind 127.0.0.1
```

Then visit `http://127.0.0.1:8765/docs/voice-managers/`.

## Updating the research

- Keep speech recognition, intent interpretation, and execution checks distinct.
- Update evidence dates when rechecking a project. Pin source links to the
  inspected commit; distinguish development features from released behavior.
- Update both project notes and comparison tables when a capability changes.
- Treat “not found” as a review limitation, not a definitive absence claim.
- The original reference reviews are in workspace `other-apps/REVIEW.md`,
  `other-apps/sources.json`, and `docs/other-voice-app-browser-notes.md`.

This page has not been published. Any public snapshot release follows
the repository's private release workflow. Before hosting it independently,
replace relative Skipper source links with reviewed public source links and
recheck claims about unreleased features.
