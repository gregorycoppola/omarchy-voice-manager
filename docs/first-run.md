# First local run — September 13, 2026

Successfully ran the Parakeet TDT 0.6B v3 INT8 community ONNX conversion on an
Apple M2 MacBook Pro (13-inch, 2022), ARM Linux / Omarchy,
kernel `7.1.13-2-1-ARCH`, Python 3.14.7.

## Memory and storage

Before setup, `free -h` reported 7.4 GiB usable physical RAM, 2.0 GiB used,
5.4 GiB available, and no swap. Disk had 35 GiB available.
The selected model files total about 639 MiB on disk.

This machine's measured peak process RSS for an 11-second clip was
**1285.6 MiB (1.26 GiB)**, including model loading and transcription. This is
not a universal RAM requirement: longer audio, batching, other runtimes and
precision settings change it. Reserve roughly 2 GiB as an initial planning
allowance for short dictation and measure again as the app grows.

For context, an independent report in the
[sherpa-onnx tracker](https://github.com/k2-fsa/sherpa-onnx/issues/2626)
measured 1.23 GB for loading an INT8 Parakeet model on iOS. That was a different
platform/runtime; the result above is our actual Linux measurement.

## Speech test

Input: 11-second JFK speech sample from
[whisper.cpp](https://github.com/ggml-org/whisper.cpp/blob/1da4dc82fa7996d4edda05890dca65aeceaafd6d/samples/jfk.wav).
The downloaded sample is local and ignored, not included in this repository.
SHA-256: `59dfb9a4acb36fe2a2affc14bacbee2920ff435cb13cc314a08c13f66ba7860e`.

Configuration: CPUExecutionProvider, four intra-op threads, one inter-op thread,
INT8 encoder and decoder, pinned model revision in `model-manifest.json`.

| Measurement | Result |
| --- | --- |
| Model loading | 0.833 seconds |
| Transcription | 0.417 seconds |
| Audio duration / transcription time | 26.38× |
| Peak process RSS | 1285.6 MiB |

Output:

> And so, my fellow Americans, ask not what your country can do for you, ask what you can do for your country.

Words matched the familiar sample. This is a functional smoke test, not a
representative accuracy evaluation or a cold-disk startup benchmark.
Loading and transcription timings exclude Python startup and imports.

The test replaced Python socket connect/connect_ex/getaddrinfo with functions
that raise on use and ran Keety through `runpy`; it passed. Keety also sets
`HF_HUB_OFFLINE=1`, uses explicit local model paths and a CPU-only provider.
This validates the exercised path without Python network access; it is not an
OS-level network sandbox.

The input-boundary test passed for stereo audio, unsupported sample rate, empty
audio, and audio exceeding 30 seconds. No microphone recording has been tested
yet. No background service or desktop shortcut was installed.

## Next hands-on test

```bash
cd ~/Projects/keety
.venv/bin/python keety.py record --seconds 10
```

Wait for “Speak now,” then speak a short sentence, including a few names or
technical terms. Inspect the transcript and the timing report. This is the
next test before building a persistent model service and push-to-talk interface.
