# Structured intents, grammars, contexts, and separate apps

Status: proposed plan, September 13, 2026. This document describes future work;
it does not change current command behavior.

Implementation progress, September 13: the first slice now includes typed
intent instances, reusable finite grammars, generated expansions, shared
exact/fuzzy parsing, and a separately launchable native GTK explorer. Existing
voice dispatch still uses compatibility action IDs. The explorer browses rules,
vocabulary, schemas, and parse evidence; it does not yet edit grammar or inspect
paired history. Contextual scopes and durable interaction history remain work
below. The compact bar popover and windowless runtime are
now implemented, with recording history/settings in Explorer. Paired intent
history and grammar editing are still pending.

## Product direction

Skipper becomes a small, everyday voice interface. Its primary surface is a
popover from the top bar, showing three things:

1. The voice waveform or amplitude visualizer.
2. The words recognized from the recording.
3. The structured intent interpreted from those words, with a readable label.

Grammar management and history inspection move into a separate companion app.
The two apps share one language system and one history. Opening the companion
must not load another speech model or create another command executor.

The central language requirement is compositionality: adding a pattern such as
`go to <destination>` makes it work for every eligible destination. Adding a
destination makes it available in every applicable pattern. Fuzzy matching
continues to work across those combinations.

## Starting point in this checkout

- `command_catalog.py` defines stable intent IDs, explicit phrase lists, and
  fixed site/app registries. Its `GRAMMAR` is a derived phrase-to-ID dictionary,
  rather than a grammar with non-terminals.
- `intent_matching.py` matches exact phrases and learned aliases, then applies
  text similarity. It groups candidates by intent ID and rejects weak or
  ambiguous matches. Accepted fuzzy phrases are remembered automatically.
- `gui.py` owns recording, transcription, matching, learning, dispatch,
  confirmations, history, and settings. Much of the coordination lives here.
- `os_actions.py` implements existing actions and captures active-window/client
  context near recording start. Context is used for targeting, but is not yet
  an explicit part of a language model or durable interpretation record.
- `recordings.py` saves WAV, transcript, and timing metadata. It does not save
  a structured interpretation and execution history.
- `launch.sh` and `config/skipper-bar/BarWidget.qml` already support background
  operation and a top-bar status button. Clicking opens the large controls UI.

Build on these foundations and preserve existing action semantics during the
first migration. The original “open chrome”/“bring up chrome” presentation distinction was
subsequently unified at the user’s request: all opened apps are maximized and
explicitly raised above the grid. Existing execution IDs remain compatible.

## Language model

### Intent schemas and intent instances

An intent schema names an operation and defines typed arguments. An intent
instance is a concrete meaning produced by the parser, independent of wording.
For example:

```json
{
  "schema_version": 1,
  "type": "open_destination",
  "arguments": {"destination": "gmail"}
}
```

“Open Gmail,” “bring up Gmail,” and eventually “go to Gmail” can all produce
this instance. The destination is a registry ID, not a spoken URL.

Start with families corresponding to current capabilities: open destination,
open application, create terminal, close window, maximize window, move window,
show windows, and tile windows. Distinguish arguments such as current window
versus most recent terminal, and preserve presentation options where needed.
The exact schema names are an implementation decision; collapsing all actions
into one generic command string would lose the structure we want.

Keep three objects separate: parsed meaning, resolved execution target, and
execution result. An intent can be valid even when its target is unavailable
or execution fails.

### Grammar and vocabulary

Author reusable rules with stable IDs and explicit bindings:

```text
rule: open_destination
patterns:
  open <destination>
  bring up <destination>
emit: open_destination(destination = <destination>.id)

<destination>:
  gmail:  Gmail | g mail
  github: GitHub | git hub
```

Vocabulary entries contain canonical IDs, display names, spoken forms, and
capabilities. Existing site URLs and app launch information remain in the
execution registry, referenced by ID. LastPass is an example future entry;
its destination and action must be configured before it becomes executable.

Rules constrain slot types and capabilities. An openable destination is not
automatically a closable browser tab. Reuse a non-terminal only where its
members support the operation.

Store the authored grammar and vocabulary as the source of truth. Generate an
inspectable expansion index containing every supported phrase, its rule,
bindings, and resulting intent. Do not maintain a second hand-edited phrase
list. Start with finite slots and complete expansion, which fits today's small
catalog. Revisit indexed slot matching if combinations become too numerous;
recursive grammars and unrestricted dictation slots are outside the first version.

Validate duplicate IDs, missing bindings, invalid arguments, unsupported
capabilities, and phrase collisions before activating a revision. Conflicting
meanings must be reported, not silently overwritten in a dictionary.

### Exact and fuzzy matching

Use the generated expansions for both exact and fuzzy matching initially. This
keeps matching behavior understandable while making shared patterns effective
everywhere. Preserve current normalization and fuzzy rejection guards as a
baseline, then evaluate thresholds against saved examples.

Group candidate scores by the complete intent instance, including arguments.
Two Gmail phrasings are the same candidate; Gmail and GitHub are competing
candidates even though both use `open_destination`. Check the winning score
and its margin over the next distinct instance. Exact collisions also remain
ambiguous unless explicit context rules disambiguate them.

Return a structured parse result: matched, ambiguous, or unrecognized; selected
intent if any; exact/fuzzy/alias match method; matched expansion; rule and
vocabulary IDs; competing candidates and scores; rejection reason; and grammar,
matcher, and context revisions. Similarity scores are not probabilities.

### Learning that generalizes

Represent three different edits explicitly:

| Learned item | Example | Effect |
| --- | --- | --- |
| Whole-phrase alias | A recurring mishearing mapped to one Gmail intent | Applies to that exact intent instance |
| Vocabulary alias | Another recognized spelling of Gmail | Applies wherever the Gmail entry is allowed |
| Grammar pattern | `go to <destination>` | Applies to all eligible destinations |

Preserve automatic whole-phrase learning initially, recording its source and
making it reversible in the companion. One fuzzy hit is not evidence that a
new rule is correct for all destinations. Provide a way to promote an example
into a vocabulary alias or shared pattern, preview its expansions and
collisions, and publish it. Automated suggestions for such promotions can come
later; the shared rule mechanism belongs in the first grammar implementation.

## Contexts

A context snapshot records facts relevant to interpreting one utterance:
focused app/window, workspace/monitor, and any explicit Skipper mode. Capture it
at recording start, before the popover can take focus. Keep target identity
stable through transcription and confirmation, and revalidate it before acting.

Rules declare where they apply. Begin with global rules plus explicit app/mode
conditions. Filter ineligible rules before matching; record which conditions
enabled or excluded a rule. If multiple eligible rules produce competing
meanings, reject ambiguity rather than introducing hidden precedence.

“This window” resolves against the captured window. A missing required context
produces an explanation rather than a guessed target. Historical inspection
uses the saved context, not the currently focused app.

Recent interactions may eventually support references such as “close it.” Defer
that to a later version with explicit reference lifetime and invalidation rules.
For the initial version, contexts are captured facts and declared scopes.

## App and runtime boundaries

| Component | Responsibility |
| --- | --- |
| Shared runtime | Own microphone/model, capture context, parse, resolve targets, execute, persist history, publish state |
| Skipper voice app | Top-bar entry and compact popover with visualizer, transcript, intent, and essential status/confirmation feedback |
| Skipper companion | Grammar/vocabulary editor, expansion explorer, parse playground, learned-item management, history and settings |

Proposed first split: two separately launchable apps, with Grammar and History
as sections of the companion. Keep those modules separate so they can become
independent apps later if useful. A local web companion is a reasonable option;
native versus web remains open until a small UI prototype settles the tradeoff.

Extract UI-independent services first. Define a local interface for runtime
state/events, paginated history, parse-only previews, and validated grammar
updates. Choose the transport when choosing the companion UI. Keep one owner
for writes and execution; publish grammar changes atomically, keep the last
valid revision on errors, and pin each recording to a revision.

If the companion is web-based, bind its server locally and restrict mutation
requests to the authorized local UI. Browsing history and testing text must
never execute commands. The companion may close while voice operation continues.

The popover should appear during recording without stealing focus, show
transcription progress, then retain the recognized words and interpreted intent
long enough to read. Final text is sufficient initially; current recognition
does not stream words. Automatic dismissal timing needs a prototype.

Move Accepted commands, Learned phrases, recording lists, playback/retry tools,
and settings into the companion. Keep essential error and terminal-close
confirmation feedback available during voice use. Access the companion and
Quit through a small menu rather than permanent panels in the popover.

## Paired recognition and intent history

Give each interaction a stable ID linking its recording and transcript to:

- Capture/transcription timestamps, original recognized text, and audio reference.
- Captured context and grammar/vocabulary/matcher revision references.
- Parse result, including unmatched/ambiguous attempts and candidate explanations.
- Selected structured intent, resolved target, confirmation outcome, and action
  result or error, with lifecycle timestamps.
- Any learned item created from the interaction and later corrections.

Save recognition and interpretation before execution, then append outcomes.
An interrupted execution remains unknown/interrupted rather than appearing
successful. Keep original interpretations immutable. Retranscription or
reparsing creates a linked analysis, never silently rewrites the historical
decision and never executes or learns from a history replay.

Retain grammar revisions referenced by history so an old result remains
inspectable after edits. Treat existing recordings as legacy history with
unknown original intent/context; do not invent those facts by reparsing them.
Migrate existing aliases to concrete structured intents through an explicit
old-ID mapping. Keep unknown or conflicting aliases visible for repair.

Proposed storage: local SQLite for history, revisions, and relationships, with
existing audio files retained separately. Finalize this in the history phase;
preserve current files and XDG locations, and make migration repeatable.

The history UI should pair “heard” and “understood” prominently. Expand a row
to inspect context, matching evidence, execution, and learning. Allow filtering
by intent, destination, context, match method, or outcome. A parse playground
can compare the original result with a chosen grammar revision without acting.

## Incremental implementation

### 1. Introduce structured intents behind current behavior

- Define intent schemas, parse results, and execution results.
- Map every existing intent ID to an instance and adapt dispatch to it.
- Extract command coordination from GTK into a shared service.
- Verify all existing phrases preserve actions, targeting, presentation, and
  confirmation behavior; run the relevant current matcher/action/GUI tests.

Done when existing commands use structured intents internally without changing
what they do, and parsing can run without constructing a GTK window.

### 2. Introduce grammar rules and typed vocabulary

- Convert eligible phrase families into rules and generate expansion indexes.
- Run exact/fuzzy matching over expansions, grouping by full intent instance.
- Add revision validation, collision reporting, and alias migration.
- Verify adding one shared pattern covers every destination, adding one
  destination covers every shared pattern, and fuzzy matching works across
  those additions while rejecting competing destinations with similar scores.

Done when the catalog no longer duplicates surrounding wording per destination
and expansion provenance is inspectable through a service or CLI.

### 3. Make context and paired history durable

- Introduce explicit context snapshots and simple rule eligibility conditions.
- Persist the interaction lifecycle and immutable grammar revisions.
- Import legacy recording references and preserve existing aliases/files.
- Verify focus changes cannot retarget an action; missing contexts and closed
  targets are explained; reparsing never executes or learns; interrupted
  interactions and migration retries remain readable and consistent.

Done when each new voice interaction explains what was heard, interpreted,
and executed, including failures and unmatched speech.

### 4. Build the companion app

- Prototype the Grammar and History views and select native or local web UI.
- Add rule/vocabulary editing, expansion preview, parse-only testing, revision
  publishing/rollback, and phrase-to-rule or phrase-to-vocabulary promotion.
- Move learning controls, history tools, and settings into the companion.
- Verify invalid edits retain the active revision and live recordings finish
  using the revision with which they started.

Done when the companion can independently inspect and manage the language
system and history, with one runtime handling recording and actions.

### 5. Replace the main window with the compact voice surface

- Reuse background/top-bar operation and expose structured runtime state.
- Build the small popover with the three primary elements.
- Remove management panels after equivalent companion tools exist.
- Verify hold-to-talk/release behavior, focus preservation, model lifecycle,
  errors, confirmations, closing either UI, and explicit quitting end to end.

Done when routine voice use needs only the small Skipper surface, and management
and inspection are available through the separately launched companion.

## Decisions to settle during implementation

- Native companion or local web app; corresponding local transport.
- Exact popover placement, persistence, and dismissal behavior.
- Initial intent schema naming and editable grammar serialization format.
- Whether future contextual rules need explicit priority beyond eligibility.
- Whether experience warrants splitting Grammar and History into separate apps.

The first implementation slice is phase 1. It makes later grammar, history,
and UI work share a concrete meaning model before changing the interface.
