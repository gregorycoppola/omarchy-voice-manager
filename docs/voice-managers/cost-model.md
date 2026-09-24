# Voice pipeline cost model

Rate snapshot: September 23, 2026. All amounts are USD, before tax and any
gateway, hosting, or regional surcharge. This is a planning calculator, not a
billing report. It makes no API requests and does not estimate accuracy.

## Scope and defaults

- 100 requested commands/day, 30 days/month.
- Three seconds of audio per attempt.
- 500 billed text input tokens and 20 text output tokens per attempt.
- No cached-input discount and no extra attempts by default.
- Text input includes instructions, schema, applicable transcript and history.
- Independent commands: no accumulating audio conversation history.
- Integrated audio models return text/function arguments only. No generated
  speech or additional transcription service is included.

These token counts are illustrative workload assumptions, not measurements from
our earlier experiment. Different tokenizers and schemas can require different
counts. Use each model's observed usage for a subsequent billing reconciliation.

## Rates

| Model | Text input / cached / output, USD per million | Audio input |
| --- | --- | --- |
| GPT-5.4-nano | 0.20 / 0.02 / 1.25 | Local ASR |
| GPT-5.4-mini | 0.75 / 0.075 / 4.50 | Local ASR |
| TypeSafe Jev cloud API | 0.042 / same rate / 0 | Local ASR |
| GPT-Transcribe + GPT-5.4-mini | Classifier rates above | $0.0045/minute |
| GPT-Realtime-2.1-mini | 0.60 / 0.06 / 2.40 | $10/million audio tokens |
| GPT-Realtime-2.1 | 4 / 0.40 / 24 | $32/million audio tokens |

Sources: [nano](https://developers.openai.com/api/docs/models/gpt-5.4-nano),
[mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini),
[OpenAI pricing](https://developers.openai.com/api/docs/pricing), and
[TypeSafe's Jev launch rate](https://typesafe.ai/blog/introducing-system-one-models-and-jev).
Rates are a dated snapshot, not automatically refreshed. The Realtime models
are cost scenarios; we have not benchmarked their latency or verified account access.

## Calculation

For text-input count I, cached fraction c, output count O, and token rates R:

```
text cost = (I × (1−c) × R_input + I × c × R_cached + O × R_output) / 1,000,000
Realtime audio cost ≈ seconds × 10 × R_audio / 1,000,000
duration-priced transcription = seconds / 60 × R_minute
per attempt = text cost + applicable audio cost
per requested command = per attempt × (1 + extra attempts per 100 commands / 100)
monthly = per requested command × commands per day × days
```

The [OpenAI accounting guide](https://developers.openai.com/api/docs/guides/voice-latency-cost)
describes input audio at roughly 10 tokens/second and notes special-token
overhead. Replace estimated counts with returned usage when available. Fresh
audio is always uncached in this calculator. The cache percentage refers only
to actually billed cached text, not merely repeated prompt content.

Extra attempts scale the average workload; this is not a probabilistic retry
model or a claim about failure rates. Cost per correct command is deliberately
absent because we have no comparable accuracy measurement.

## Default monthly estimates

| Candidate | API fee / 3,000 requested commands |
| --- | ---: |
| Local speech + local rules / LLM | $0.0000 |
| Local speech + local Jev-style classifier (e.g. Kev) | $0.0000 |
| Local speech + TypeSafe Jev cloud API | $0.0630 |
| Local speech + nano | $0.3750 |
| Local speech + mini | $1.3950 |
| Integrated Realtime-2.1-mini | $1.9440 |
| GPT-Transcribe + mini | $2.0700 |
| Integrated Realtime-2.1 | $10.3200 |

Local speech has no API fee regardless of recognizer. A local Jev-style classifier
(such as [Kev](https://github.com/jaredpalmer/kev)) also has no API fee;
TypeSafe Jev in the cloud is a separate paid option.

Local API fees exclude electricity, hardware, model residency, and engineering.
Optional local running and training budgets are entered separately. Blank
means unknown, not zero. Training allocation = one-time budget / chosen months;
it is not charged on every attempt. No accuracy-equivalent break-even is claimed.

## Reproduction

The browser uses [cost-model.js](cost-model.js). To check known scenarios,
cache treatment, retry scaling, zero use, and invalid input handling:

```sh
node tests/test_voice_cost.cjs
```

For future real requests save input text/audio counts, cached counts by modality,
output counts including billed reasoning if applicable, model snapshot, rate
date, and request IDs. Separate calculated usage cost from retrieved billing.
