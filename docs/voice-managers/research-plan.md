# Speech-to-intent: latency, accuracy, cost, and adaptation

Status: research design, September 23, 2026. No new experiments or training
were run to prepare this plan.

Current scope: latency and cost modeling. Accuracy evaluation below is a future
track, not an available input to the calculator. See [cost-model.md](cost-model.md)
for the implemented cost scenarios. Do not infer accuracy, an error rate, or cost
per correct result from those scenarios.

## Objective

Model and measure the latency of local, hybrid, and cloud voice-command
pipelines. Seek the best accuracy with low response time and low user cost.
Treat current off-the-shelf accuracy as an improvable baseline: investigate
whether training smaller models for the task improves the tradeoff.

The existing voice managers are architecture references, not the only candidates.
Keep component experiments separate from reproductions of a complete product.
A minimal model prompt does not measure OMA's or Omarvis's actual behavior.

## Candidate matrix

| Recognition | Interpretation | Purpose |
| --- | --- | --- |
| Local | Authored rules | Existing deterministic baseline |
| Local | Local small model | Fully local model pipeline |
| Local | Cloud model | Local recognition with hosted interpretation |
| Cloud | Rules or local model | Isolate the recognition placement tradeoff |
| Cloud | Cloud model | Two-stage hosted pipeline |
| Integrated audio model | Joint audio-to-intent output | Streaming conversational architecture |

Within each applicable row, vary model, model size, quantization, hardware,
streaming mode, prompt/context length, and baseline versus trained checkpoint.
Start with a small pilot rather than the full combinatorial matrix. Hold the
supported intents, argument schemas, target context, and scoring policy fixed.

## Measurement contract

Use a monotonic clock for client events. Record offsets, not cross-machine
wall-clock subtraction. For each attempt, capture where observable:

- Last speech sample, capture stop/commit, and request dispatch.
- Recognition start and final transcript receipt.
- Classifier start, complete intent receipt, and validation completion.
- Action dispatch, observed completion, and first visible or audible feedback.
- Clarification, confirmation, retries, failure, cancellation, and timeout.

Primary latency: **last speech sample → validated intent ready**.
Secondary latency: **last speech sample → observed action completion**.
Also report capture-commit → intent latency to distinguish human release delay
from processing. Report first-feedback latency separately.

For sequential pipelines, component spans explain the total. Request wall time
already includes network, queueing, and provider processing; do not add those
again. Without server instrumentation, these internal contributions are unknown.

For streaming pipelines, replay audio at real-time cadence and calculate the
critical path from event timestamps. Work can overlap speech and other stages.
Do not treat a batch upload as equivalent to a live session. Integrated audio
models may not expose distinct recognition and classification spans.

Keep cold connection/model startup separate from warm requests. Record prompt
cache state when exposed and retain first requests. Report p50 and p95 from
actual complete-pipeline samples, plus sample counts, failures, and timeouts.
Never describe sums of component medians or p95 values as measured percentiles.
Track confirmation time and correction turns explicitly rather than attributing
human waiting to model inference.

## Accuracy and user cost

Score recognition against independently reviewed transcripts. Report WER and
errors in command-critical words: action, object, number, and negation.
Score interpretation against independently labeled full intents and arguments.
Separate wrong actions, unnecessary rejections, and appropriate clarification.
Evaluate classifiers on both gold transcripts and actual recognizer output.

Record latency for successes and failures separately without dropping failures
from the study. Measure eventual correct completion including recovery where
possible. Fast incorrect actions must not win a latency-only ranking.

Record provider/model version, service tier, usage units, rate source/date,
request count, and calculated cost versus actual billing when available.
For local inference record device, threads, peak memory, CPU/GPU use, and energy
only when measured. No API fee is not the same as no user cost.

Report cost per attempt and per correctly completed task, plus monthly scenarios
with explicit command frequency, audio length, context size, and retry rate.
Keep hardware purchase assumptions, labeling, training, and deployment costs
separate. Estimate training break-even only with stated usage assumptions.

## Adaptation experiments

1. Establish untouched baselines and collect representative command recordings.
2. Split train/validation/test before tuning. Group by session and phrasing family;
   hold out speakers for general-user claims. Track personal adaptation separately.
3. Test recognition vocabulary/context support where available, then evaluate
   acoustic adaptation for models with a suitable training path.
4. Compare intent prompting, supervised fine-tuning/LoRA, and distillation from
   a larger teacher. Review teacher labels; include rejection and ambiguity cases.
5. Test each trained checkpoint against its own untrained baseline, keeping
   inference settings fixed. Study quantization independently afterward.
6. Rerun the full audio-to-intent pipeline on held-out data and target hardware.

Hypothesis: adaptation may improve the accuracy of a faster/cheaper model enough
to make it preferable. Neither recovery of accuracy nor latency improvement is
assumed. Retain larger/cloud models as reference points.

## Existing evidence and next measurements

- [Intent comparison](../../experiments/command-comparison-results.md): 24 unique
  cases, three repeats per model. Useful component pilot, not product latency.
- [Existing experiment runner](../../experiments/README.md): local Qwen and
  OpenAI text-only comparison. It never executes selected actions.
- [Transcription runner](../transcription-benchmark.md): Parakeet versus
  ElevenLabs Scribe v2 on identical WAVs. This measures dictation, not Omarvis's
  conversational agent. OpenAI speech support would be a separate extension.
- Historical Skipper metadata summarized September 23: 547 entries, median
  transcription 130 ms, p95 169 ms. Uncontrolled observations, not a fixed corpus.

Next: instrument a common event/report format, benchmark the local rules baseline,
prepare a labeled non-sensitive audio corpus, then measure local and hosted
component combinations. Keep generated intents in a capture-only executor for
classification tests. Run visible-action measurements separately with repeatable
reversible tasks. Preserve raw reports locally and publish only reviewed aggregate
results with their evidence labels and reproduction settings.

The comparison page should label every number as a **measured component**,
**measured pipeline**, **historical observation**, or **estimate**. Missing data
stays **not measured**. Training results get separate baseline and adapted rows.
