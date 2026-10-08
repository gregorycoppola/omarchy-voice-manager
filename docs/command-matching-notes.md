# Command matching notes

Update, October 2: the picker now groups commands by shared prefixes. Verb roots
use substring matching (exact verb wins); one matching branch reveals its
children automatically. The text scorer below ranks remaining choices within
the current level. Prefix uniqueness is decided before display truncation.
See [the current picker design](argument-picker-design.md) for Tab, Enter, Back,
lazy child construction, and website argument providers.

The command picker first filters by normalized ordered-character subsequence, then reranks
a shortlist using the existing fuzzy text score. Frequency is
an independent signal exposed for inspection, with no influence on ordering,
even when text scores tie. This is the initial text-only baseline for tuning.

## Code and scope

[CommandSearch.js](../config/skipper-bar/CommandSearch.js) implements
`textMatchScore`, `frequencyScore`, `rank`, and the UI adapter `search`.
[BarWidget.qml](../config/skipper-bar/BarWidget.qml) calls `search`.
[Runtime](../runtime.py) supplies supported static and dynamic options, including
window and installed application commands. Each option has default text and
optional alternative forms. The picker searches these supported phrases;
arbitrary history strings do not become suggestions.

## Text match score

Both the query and each candidate phrase are lowercased and have all whitespace
removed. Punctuation remains. A dynamic programming alignment finds the minimum
cost to turn the query into the candidate using these operations:

| Operation | Cost |
| --- | --- |
| Match identical characters | 0 |
| Insert a candidate character skipped by the query | 0.25 |
| Delete an extra query character | 1 |
| Substitute a different character | 1 |
| Transpose two adjacent characters | 0.75 |

Cheap skipped candidate characters allow abbreviations and unfinished typing.
The score itself can compare transpositions, but the subsequence filter now
rejects `open chrmoe` before scoring `open chrome`. This is a weighted edit
alignment with restricted adjacent transpositions: transpositions use the cell
two rows and two columns back when the two characters cross-match. It is not
an unrestricted sequence of overlapping transpositions.

For normalized query length Q, candidate length C, and minimum cost D:

`textScore = max(0, 1 - D / (Q + 0.25 * C))`

The denominator is the cost of deleting the entire query and inserting the
entire candidate. Empty queries or candidates receive score 0. An exact
normalized match gets 1 naturally from zero edit cost. There are no exact,
prefix, substring, or subsequence tiers, and no prefix bonus. For example,
`open zz` and `zz open` score equally for `open`.

The recurrence takes the minimum of the cell above plus 1, the cell to the left
plus 0.25, the diagonal plus 0 or 1, and the eligible transposition cell plus
0.75. Initial row costs are `0.25 * j`; initial column costs are `i`.
Time is O(Q * C) per phrase, and rolling rows use O(C) memory.

The edit costs are initial heuristic settings, not measured probabilities.
The previous 0.55 cutoff has been removed: a valid subsequence match remains
eligible even when its full-phrase score is low.

## Independent frequency score

`frequencyScore` currently exposes the nonnegative raw count of recognized
typed attempts for the command, or zero if absent or invalid. Counts come from
[CommandStore.written_counts](../command_store.py), loaded when the picker opens.
They are shared across a command's forms, have no recency decay, and are
recorded after recognition rather than after successful execution.

The current ranker never reads frequency when sorting. Raw counts are not on
the same scale as the 0–1 text score; a future blended ranking would need an
explicit transformation and weighting policy. No such blend is enabled yet.

## From scores to displayed options

1. Lowercase the query and remove all whitespace. Scan default phrases and
   forms using the same normalization and a linear ordered-character scan.
2. Reject options with no subsequence match. For each surviving option, retain
   its shortest matching form. With the current edit costs this is also its
   highest scoring subsequence form. Equal lengths retain the earlier form.
3. Sort cheaply by matching form length, then original catalog order.
   Deduplicate lowercase displayed text and retain at most **50** options.
4. Compute the deeper text score for those options only, then sort by descending
   score with original catalog order breaking ties. Frequency has no influence.
5. Display at most **10** choices.

Empty input skips scoring and retains the first 50 unique default phrases in
catalog order. `rank` exposes the shortlist with both signals and original
indices; `search` returns the first ten displayed strings. Argument branches
use the same ranking but keep stable labels.

Subsequence filtering allows gaps: `list windows` matches `list all windows`,
and `opn` matches `open`. Every query character must occur in order; repeated
characters require distinct occurrences. `windows list` cannot match `list all
windows`, and `chrmoe` still cannot match `chrome`. Case and whitespace are
ignored. There is no prefix tier or automatic typo fallback.

The filter scans each normalized candidate once, taking O(candidate length)
time with constant extra matching state. The existing edit score is applied to
at most 50 retained options. With these edit costs, a subsequence match needs
only candidate insertions, so its score depends on the length difference. The
bounded deeper stage remains available for future scoring changes.

## Argument levels and Enter

The picker applies matching within the current level. Verb roots use substring
matching and prefix inference can reveal a unique branch while typing. Tab
accepts a choice and advances. Enter advances a non-executable branch or runs a
completed command. Executable app and tile-category branches run their current
defaults on Enter; Tab reveals optional arguments. See the
[argument picker design](argument-picker-design.md) for controls and scope.

Ctrl+Enter clears explicit row selection and calls the same submission handler.
It does not bypass unfinished argument levels or branch handling.

## The separate command parser

`IntentMatcher.parse` first normalizes by lowercasing, collapsing whitespace to
single spaces, and stripping spaces and `. ! ?` from the ends. This differs
from the picker's removal of all whitespace. It handles explicit grammar,
aliases, dynamic expansions, browser spelling rules, and free text or numeric
command patterns before general fuzzy matching. Multiple exact meanings are
ambiguous. The runtime enables saved corrections for speech, not typed input.

For eligible fuzzy candidates it uses Python's
`difflib.SequenceMatcher(None, phrase, candidate.phrase).ratio()`. The ratio is
`2 * M / (len(phrase) + len(candidate.phrase))`, where `M` is the total length
of matching blocks selected by SequenceMatcher. This is character similarity,
not a probability of intent correctness or an edit distance.

Window and application movement candidates additionally compare the command
frame and target name separately, taking the minimum of those scores and the
whole phrase score. Window candidates also compare names with trailing
`terminal`, `window`, or `codex` removed. Each intent keeps its highest scoring
phrase. The top intent must score at least **0.72**, and must lead the next
intent by at least **0.06**; otherwise the result is unrecognized or ambiguous.

Eligibility restrictions matter: custom actions, installed application
candidates, and commands marked exact only are excluded from general fuzzy
matching. Negation, phrase length, hide commands, and certain named target
requests also constrain or block fallback. Ordinary fuzzy input needs 2–8
words; a qualifying named move request allows up to 16. Consult `parse` for
the complete precedence and guards before changing this second algorithm.

## Notes for tuning

Start by collecting query → intended option → actual first option examples and
examining text scores alone. Include abbreviations, transposed letters, longer
window titles, short queries, and unrelated inputs. Candidate availability is
separate from ranking: an option omitted by the runtime cannot be ranked.

The next tuning targets are shortlist size and the deeper scoring formula. The current formula treats skipped characters equally wherever
they occur: it has no word boundary, contiguous run, or semantic bonus. Removing
whitespace also lets matches cross word boundaries. Long candidates accumulate
skip costs and rank below shorter matches.

After the lexical baseline is useful, evaluate frequency independently. A later
policy could use frequency only on exact lexical score ties, as requested, or
introduce an explicitly tuned blend. Keep those experiments separate so history
cannot conceal lexical ranking problems. The text-only baseline currently uses
catalog order for ties, allowing its behavior to be evaluated without history.

[Picker tests](../tests/test_command_search.cjs) cover strict subsequence filtering, bounded deeper scoring, partial
input, independent signals, frequency invariance including ties and empty
input, alternative forms, dynamic options, deduplication, and the result limit.
