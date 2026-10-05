# Voxtype speech backend plan

Direction, October 2, 2026: **text/dropdown first, voice later**. Voice remains
part of Skipper's goal. The custom Parakeet integration, recording loop, model
downloader, and hold-to-talk controls have been removed. No Voxtype adapter has
been implemented yet. Existing recordings and downloaded weights are preserved.

## Default and optional voice lifecycle

Typing and dropdown menus are always the default. Starting Skipper must not
start Voxtype or load any speech weights. A later voice integration is opt-in.
Provide an explicit disable/unload action that cancels recognition and releases
the model process while the command picker continues running. Idle unloading
may be added, but disabling voice must not depend on waiting for an idle timer.
Distinguish a Skipper-owned worker from an independently managed Voxtype daemon;
never stop another app’s shared daemon without an explicit user decision.

## Responsibility boundary

Skipper owns the command catalog, text matching, explicit argument levels,
window targeting, confirmations, execution, and history. It accepts text through
its shared interpretation path; it should not own speech model inference.

A future external speech adapter supplies recognized text to that same system.
Capture the intended window before opening a voice UI, retain request identity,
and apply the same incomplete-argument and confirmation rules as the picker.
Voice must not bypass those rules. Start with transcript preview and explicit
acceptance before considering automatic execution.

Evaluate Voxtype's supported output or file-transcription interface before
choosing microphone ownership. Prefer external capture if it supports the needed
context and cancellation behavior; do not rebuild the old custom recorder by
default. Capture output directly rather than typing into the focused app or
using clipboard contents as command transport. Disable optional text rewriting
for the initial integration.

No direct Parakeet fallback remains in Skipper. Missing or failed external
recognition should leave the command unexecuted and keep text input available.

## Verified local starting point

- The machine is aarch64, with 7.4 GiB of RAM.
- `/usr/bin/voxtype` is installed at version 1.0.1 and resolves to
  `/usr/lib/voxtype/voxtype-cpu`.
- `voxtype transcribe --help` accepts a mono 16 kHz WAV and an engine override.
- The local model catalog reports Whisper `base.en` installed. It does not
  report a Parakeet model installed in Voxtype's model directory.
- `voxtype info engines` marks Whisper compiled and active; the other listed
  engines are not marked compiled in this binary. Listing an engine in CLI
  help does not establish that this binary can run it.
- `voxtype info variants` gives x86-oriented advice inconsistent with this ARM
  host, and flags its installed ONNX native variant as incompatible. Treat that
  report as unresolved; verify the actual ARM build and dependencies.
- Skipper currently runs in keyboard-only mode. Its prior loaded Parakeet
  process used approximately 1 GiB; restarting without speech reduced its
  proportional memory to approximately 36 MiB in the observed session.

## Implementation sequence

1. **Compatibility pilot.** Use a short, known local WAV to verify transcript
   output, process exit status, stderr/stdout separation, cancellation, and
   failure behavior with the installed Whisper build. Determine the suitable
   ARM Parakeet build and model layout. Confirm whether existing model assets
   can be reused; do not assume format compatibility from the model name.
2. **Adapter.** Add an explicit backend choice and subprocess adapter with an
   argument list, bounded execution time, cancellation, and actionable errors.
   Preserve original recordings, transcripts, capture context, and the typed
   picker. Check that a failed recognizer cannot cause command execution.
3. **Recognition comparison.** Replay identical recordings through Whisper,
   Voxtype Parakeet when a compatible build is available. Compare with saved historical measurements where useful. Measure cold and
   warm latency separately, peak and idle memory, transcript errors, and
   command/argument correctness. Begin with capture-only execution.
4. **Choose the lifetime policy.** A per-request process is a simple initial
   interface but may reload weights every time. If that delay is excessive,
   investigate a documented reusable worker or daemon interface with idle
   eviction. Do not assume the file-transcription command uses the daemon's
   resident model or its idle-unloading policy.
5. **Controlled rollout.** Enable speech explicitly only after the pilot works.
   Test repeated requests, cancel/quit, stale window targets, missing models,
   and coexistence with ordinary dictation. Choose measured idle-memory and
   command-latency targets before making it the default speech backend.

## Tradeoffs

Voxtype centralizes engine selection and recognition infrastructure, reducing
Skipper's direct model-runtime integration work. It is an application and CLI
dependency rather than a guaranteed stable Python library API: releases, binary
variants, output behavior, and configuration need compatibility checks.

The model still consumes memory during inference. Moving it to another process
does not remove that cost. Unloading saves idle memory at the expense of the
next request's startup delay. Two independent dictation/command daemons could
also load duplicate models; shared residency is a future interface question.

Engine features differ. Streaming, language support, prompt hints, acceleration,
model formats, and timestamps cannot be assumed identical across Whisper and
Parakeet. Optional replacements or LLM rewriting may change command meaning;
evaluate them separately from raw transcription.

## Sources

- [Voxtype features and engines](https://voxtype.io/): Whisper and Parakeet
  support, model variants, and on-demand loading.
- [Voxtype release notes](https://voxtype.io/news/): 1.0.1 idle-eviction fix and
  1.1.0 changes to text processing across transcription paths. Installed 1.0.1
  behavior must not be inferred from 1.1.0 documentation.
- Local `voxtype --help`, `transcribe --help`, `info engines`, `info variants`,
  and `info models`, inspected October 2, 2026. No transcription was run.
- Historical direct-backend measurements are retained in the repository docs. The custom backend source has been removed.
