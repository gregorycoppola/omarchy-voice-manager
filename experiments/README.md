# Small-model command experiments

This is a standalone, text-only pilot. It does not load recordings, change
Skipper's parser, or execute model-selected commands. Run from the private repo.

The first model is [Qwen3.5 0.8B](https://huggingface.co/Qwen/Qwen3.5-0.8B),
using the llama.cpp team's Q4_0 GGUF conversion (563,036,064 bytes).
Quantization and model size are separate variables: this pilot measures this
specific quantization, not the original full-precision model.

Pinned artifacts:

- Runtime: [llama.cpp b11090, Ubuntu ARM64 CPU](https://github.com/ggml-org/llama.cpp/releases/tag/b11090).
  Archive SHA-256: `5671d66fe37e7a3fb114535dc055aba91e99427c82d15dd95d0ad4d887f13c89`.
- Model: `ggml-org/Qwen3.5-0.8B-GGUF`, revision
  `8fea620810c4afa23dd6443f999a48574c1611a3`, file `Qwen3.5-0.8B-Q4_0.gguf`.
  SHA-256: `57d1997790d1744fba5b40a7317df71ea5e2acee28c47e78f0cce39c0703f8cf`.

The downloaded runtime lives in ignored `local/qwen-experiments/runtime/`;
weights live in ignored `models/qwen/`. Start it with:

```bash
local/qwen-experiments/runtime/llama-b11090/llama-server \
  -m models/qwen/Qwen3.5-0.8B-Q4_0.gguf \
  --host 127.0.0.1 --port 18089 -c 2048 -np 1 -t 4 -ngl 0 --reasoning off
```

Then, in another terminal:

```bash
python experiments/qwen_commands.py \
  --model Qwen3.5-0.8B-Q4_0 \
  --output local/qwen-experiments/qwen35-08b-pilot.json
```

Stop the server with Ctrl+C afterward to release memory. The script uses only
Python's standard library. Each request is independent; server prompt caching
can reuse the common system prompt. Timing is wall time including HTTP and
generation, excludes model loading, and includes the first request. Background
activity can affect it. Generation is greedy, limited to 128 tokens, with thinking
disabled and no JSON grammar constraint. A pass requires exactly the expected
JSON object and a normal completion; format errors and truncation count as failures.

The 24 authored cases cover literal commands (5), paraphrases (10), and rejection
(9). They exercise only ten audio/brightness/media intents. This is a smoke
experiment, not a reliable estimate of real-world accuracy or full Skipper coverage.
The rejection policy is explicit: multiple actions and exact numeric settings
are unsupported, even when a related single-step action exists.

## Finding the smallest usable model

1. Define the task and acceptance threshold first. For command routing, track
   correct intent plus arguments, unsupported-request false actions, format
   validity, latency, and peak memory separately. Evaluate ASR mistakes separately
   from correct text. Compare against Skipper's current parser on the same scope.
2. Build a larger labeled set from realistic requests. Split by phrasing family
   and recording/session before any tuning, so near-duplicates do not leak.
   Reserve an untouched final test set. These public-in-repo pilot cases are
   development examples, not an untouched final test set.
3. Compare sub-billion, roughly 2B, and roughly 4B instruction models, one at a
   time where memory permits. Hold prompt, context, quantization, and inference
   settings constant where possible. Check a higher-precision variant before
   attributing a failure entirely to parameter count.
4. Compare zero-shot, a few examples in the prompt, and constrained JSON output
   before training. Format constraints cannot establish semantic correctness.
5. Fine-tune a small candidate with LoRA on a separate training set; choose
   settings on validation data. Use a suitable GPU elsewhere if local training
   is impractical. Then quantize and rerun the identical held-out evaluation on
   this machine. Compare against both its untuned version and larger models.

The minimum viable fine-tuned size is an experimental result. Do not infer it
from this pilot or promise that specialization will recover general reasoning.

## First run: 2026-09-21

Apple M2, aarch64 Linux, 8 logical CPUs, 7.4 GiB usable RAM. CPU inference,
four generation threads, 2,048-token context, one slot, commands as above.

| Category | Current parser | Qwen3.5 0.8B Q4_0 |
| --- | ---: | ---: |
| Literal commands | 5/5 | 5/5 |
| Paraphrases | 0/10 | 6/10 |
| Correct rejections | 9/9 | 5/9 |
| Total | 14/24 | 16/24 |

The parser baseline used `IntentMatcher` with temporary empty alias, correction,
and custom-action stores and no dynamic windows/apps. Audio/brightness/media
commands intentionally require exact authored wording in the current parser.
The model's better paraphrase coverage came with four false actions on rejection
cases, so the aggregate score does not justify replacing the parser.

Model request latency: median 0.177 s, maximum/first request 0.571 s. Server RSS
sampled after the run was 1,320,880 KiB (about 1.26 GiB); this is not peak memory.
All 24 outputs were valid JSON. Important failures:

- “Take the speakers off mute” selected mute instead of unmute.
- “Silence the speakers please,” “Put playback on hold,” and “Go back to the
  song before this one” incorrectly returned no action.
- A hypothetical mute question, quoted “next track,” a two-action request, and
  an instruction to override the rules incorrectly selected actions.

Raw local reports: `local/qwen-experiments/qwen35-08b-pilot.json` and
`local/qwen-experiments/parser-baseline.json`. Downloads were checked against
the SHA-256 values above. This is one greedy run of a tiny authored development
set; no fine-tuning, few-shot prompt tuning, or larger-model comparison was done.

## OpenAI comparison

`compare_commands.py` imports the exact same `SYSTEM` and `CASES` from
`qwen_commands.py`. Gold answers are authored in `CASES` before inference;
OpenAI is evaluated against them, not used to grade itself or Qwen.
The script loads `OPENAI_API_KEY` from workspace-root `../.env.local` without
shell execution or printing credentials. API requests go only to
`https://api.openai.com/v1/chat/completions`. Only the authored prompt and case
text are sent. Generated actions are never executed.

Start the local server as above, then run:

```bash
python experiments/compare_commands.py --include-local --repeats 3 \
  --output local/qwen-experiments/openai-comparison.json
```

This makes 72 paid requests to each of `gpt-5.4-nano` and `gpt-5.4-mini`, plus
72 local requests. Omit `--include-local` to test only OpenAI. Requests are
sequential, interleaved between models, and case order is shuffled reproducibly
for each pass. Each model has a reusable HTTP connection. Request latency
includes connection setup when needed, network transit, server time, and the
complete response body; it excludes file writes, audio transcription, action
execution, and local model loading. First requests are retained in the statistics.

All models get temperature zero, at most 128 output tokens, no few-shot examples,
no conversation history, and no constrained JSON decoder. Qwen uses seed 42 and
thinking disabled; OpenAI uses `reasoning_effort=none` and no seed. Reported model
snapshots and token usage are saved with each response. The script does not force
a service tier; the API account/project default applies. Transport and API errors
are saved and stop the run without automatic retries. Results are saved after
every response, so an interrupted run is identifiable by its smaller counts.

Three repeats measure variation on 24 unique cases, not 72 independent examples.
The p95 uses the nearest-rank sample percentile. This sample cannot establish
production accuracy, stable internet latency, or general-purpose intelligence.
Greedy decoding can still vary with backend numerical behavior and caching.
