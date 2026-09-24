# Parakeet vs. Omarvis dictation benchmark

This evaluates transcription only: Skipper's pinned local Parakeet model against
Omarvis's ElevenLabs Scribe v2 dictation backend. It does not test Omarvis's
conversational agent, desktop actions, or text insertion.

## Corpus

Create a directory ignored by Git, for example `local/benchmark/`, with 30–50
short WAV clips and a reviewed reference transcript for each one. Use the same
mono 16-bit PCM 16 kHz WAV inputs Skipper accepts; keep clips at 30 seconds or
shorter. Include ordinary commands, proper names, app names, window titles,
numbers, negations, and a little natural dictation. Do not include sensitive
speech: the ElevenLabs run uploads every selected WAV.

`local/benchmark/manifest.json`:

```json
{
  "clips": [
    {
      "id": "open-chrome-01",
      "wav": "open-chrome-01.wav",
      "reference": "open chrome"
    }
  ]
}
```

References should be written or independently reviewed before inspecting either
system's outputs. Keep the corpus fixed for a round of comparisons.

## Run

Run Parakeet first; this stays entirely local:

```bash
cd ~/Projects/omarchy-voice-manager/private
.venv/bin/python benchmark.py local/benchmark/manifest.json \
  --backend parakeet --output local/benchmark/parakeet.json
```

Run the hosted comparison only after deliberately setting a scoped ElevenLabs
key in the current shell. This sends each corpus WAV to ElevenLabs Scribe v2:

```bash
export ELEVENLABS_API_KEY='...'
.venv/bin/python benchmark.py local/benchmark/manifest.json \
  --backend elevenlabs --output local/benchmark/elevenlabs.json
unset ELEVENLABS_API_KEY
```

The two JSON reports retain each transcript and per-clip timing. Compare their
summary values: corpus-level word error rate (WER), exact-clip rate, and median
transcription duration. Lower WER and duration are better. Read individual
errors as well: for desktop control, a wrong app name or missed negation matters
more than a punctuation difference that WER intentionally ignores.

For a repeatable cost figure, record total corpus duration beside the results.
The runner sends no prompts, screenshots, window metadata, or desktop commands;
only the WAV upload and model identifier are in the hosted request.
