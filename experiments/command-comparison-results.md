# Command classification comparison

Run: 2026-09-22T00:20:30.988332+00:00

Gold answers were authored before inference. Same 24 unique requests and system prompt, repeated three times per model (72 responses each). No fine-tuning or prompt changes.

| Model | Correct | Accuracy | Median | p95 | False actions on 27 rejection trials |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qwen3.5-0.8B-Q4_0 | 48/72 | 66.7% | 0.185 s | 0.206 s | 12 |
| gpt-5.4-nano | 65/72 | 90.3% | 0.562 s | 1.239 s | 4 |
| gpt-5.4-mini | 72/72 | 100.0% | 0.496 s | 0.860 s | 0 |

## Category scores

| Model | Literal | Paraphrase | Reject |
| --- | ---: | ---: | ---: |
| Qwen3.5-0.8B-Q4_0 | 15/15 | 18/30 | 15/27 |
| gpt-5.4-nano | 15/15 | 27/30 | 23/27 |
| gpt-5.4-mini | 15/15 | 30/30 | 27/27 |

## Mistakes

Qwen repeated the same eight errors in all three passes: mute instead of unmute; rejection of silence speakers, hold playback, and previous-song paraphrases; false actions on hypothetical, quoted, multiple-action, and override requests.

Nano rejected “Put playback on hold” and acted on the hypothetical mute question in all three passes. It also acted on quoted “next track” in one pass. Mini made no errors in this pilot.

## Timing and cost

Median time includes the complete response, including network time for OpenAI. The local model was already loaded. All requests were serial and model-interleaved, using persistent HTTP connections; first connection requests are included. These timings exclude audio transcription and desktop execution. Mini was faster than nano in this run; that is not a general latency guarantee.

OpenAI returned snapshots `gpt-5.4-nano-2026-03-17` and `gpt-5.4-mini-2026-03-17`, both on service tier `default`. No HTTP errors or truncated outputs occurred.

Estimated token costs at the documented standard rates: nano $0.003403; mini $0.012625; total **$0.016027** (about 1.6 US cents). Both used 12,819 input tokens, zero cached input tokens; output totals were 671 and 669 respectively. These are calculated costs, not a retrieved billing charge.

Pricing sources: [nano](https://developers.openai.com/api/docs/models/gpt-5.4-nano), [mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini).

## Reproduction and limits

See [README](README.md#openai-comparison) and [runner](compare_commands.py). Exact inputs, gold answers and system instructions are in [qwen_commands.py](qwen_commands.py). Raw responses, timing, request IDs, and token usage are in ignored `local/qwen-experiments/openai-comparison.json`.

This is a small authored development pilot. Three repeats do not increase coverage beyond the 24 unique requests. Perfect performance here does not establish production accuracy. Numeric settings and multiple actions are explicitly unsupported by the prompt, so null is the intended answer for those cases. Model output was scored by exact parsed JSON equality and normal completion. No model outputs were executed as desktop actions.
