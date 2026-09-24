"""Compare local Parakeet and ElevenLabs Scribe transcripts on the same WAV corpus.

The corpus is deliberately local and ignored by Git.  ElevenLabs is contacted
only when its backend is selected explicitly.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import statistics
import time
import urllib.error
import urllib.request
import uuid

from skipper import load_model, recognize_file


def normalize(text: str) -> list[str]:
    """Return a deliberately simple, punctuation-insensitive WER token stream."""
    return [word for word in "".join(
        char.lower() if char.isalnum() or char in "' " else " " for char in text
    ).replace("'", "").split() if word]


def distance(expected: list[str], actual: list[str]) -> int:
    """Levenshtein edit distance, measured in words."""
    previous = list(range(len(actual) + 1))
    for index, expected_word in enumerate(expected, 1):
        current = [index]
        for actual_index, actual_word in enumerate(actual, 1):
            current.append(min(
                previous[actual_index] + 1,
                current[actual_index - 1] + 1,
                previous[actual_index - 1] + (expected_word != actual_word),
            ))
        previous = current
    return previous[-1]


def score(expected: str, actual: str) -> dict[str, object]:
    reference = normalize(expected)
    if not reference:
        raise ValueError("Reference transcript must contain at least one word.")
    edits = distance(reference, normalize(actual))
    return {"reference_words": len(reference), "word_edits": edits,
            "wer": edits / len(reference), "exact": normalize(expected) == normalize(actual)}


def read_manifest(path: Path) -> list[dict[str, str]]:
    data = json.loads(path.read_text())
    clips = data.get("clips") if isinstance(data, dict) else None
    if not isinstance(clips, list) or not clips:
        raise ValueError("Manifest needs a non-empty 'clips' list.")
    result = []
    for item in clips:
        if not isinstance(item, dict) or not all(isinstance(item.get(key), str) and item[key].strip()
                                                  for key in ("id", "wav", "reference")):
            raise ValueError("Every clip needs non-empty string id, wav, and reference fields.")
        result.append({key: item[key] for key in ("id", "wav", "reference")})
    return result


def parakeet_transcriber(threads: int):
    model, load_seconds = load_model(threads)

    def transcribe(path: Path) -> tuple[str, dict[str, object]]:
        return recognize_file(model, path, load_seconds)
    return transcribe


def multipart_body(path: Path, boundary: str) -> bytes:
    """Build the minimal multipart request required by ElevenLabs Scribe v2."""
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"model_id\"\r\n\r\nscribe_v2\r\n".encode(),
        (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
         f"filename=\"{path.name}\"\r\nContent-Type: audio/wav\r\n\r\n").encode(),
        path.read_bytes(), b"\r\n", f"--{boundary}--\r\n".encode(),
    ]
    return b"".join(parts)


def elevenlabs_transcribe(path: Path, api_key: str) -> tuple[str, dict[str, object]]:
    boundary = f"skipper-{uuid.uuid4().hex}"
    request = urllib.request.Request(
        "https://api.elevenlabs.io/v1/speech-to-text",
        data=multipart_body(path, boundary), method="POST",
        headers={"xi-api-key": api_key,
                 "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"ElevenLabs transcription failed (HTTP {error.code}): {detail}") from error
    transcript = payload.get("text")
    if not isinstance(transcript, str):
        raise RuntimeError("ElevenLabs returned no transcript text.")
    return transcript, {"transcribe_seconds": round(time.perf_counter() - started, 3),
                        "provider": "ElevenLabs Scribe v2"}


def run(manifest_path: Path, backend: str, threads: int, output: Path) -> dict[str, object]:
    clips = read_manifest(manifest_path)
    root = manifest_path.parent
    if backend == "parakeet":
        transcribe = parakeet_transcriber(threads)
    else:
        api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
        if not api_key:
            raise ValueError("ELEVENLABS_API_KEY is required for --backend elevenlabs.")
        transcribe = lambda path: elevenlabs_transcribe(path, api_key)

    results = []
    for clip in clips:
        wav = (root / clip["wav"]).resolve()
        if not wav.is_file():
            raise ValueError(f"Missing audio for {clip['id']}: {wav}")
        transcript, metrics = transcribe(wav)
        results.append({"id": clip["id"], "reference": clip["reference"], "transcript": transcript,
                        "metrics": metrics, "score": score(clip["reference"], transcript)})

    total_words = sum(item["score"]["reference_words"] for item in results)
    total_edits = sum(item["score"]["word_edits"] for item in results)
    report = {"backend": backend, "manifest": str(manifest_path), "clips": results,
              "summary": {"clip_count": len(results), "wer": total_edits / total_words,
                          "exact_clip_rate": sum(item["score"]["exact"] for item in results) / len(results),
                          "median_transcribe_seconds": statistics.median(
                              item["metrics"]["transcribe_seconds"] for item in results)}}
    output.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="JSON corpus manifest")
    parser.add_argument("--backend", choices=("parakeet", "elevenlabs"), required=True)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args.manifest, args.backend, args.threads, args.output)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        parser.exit(1, f"Benchmark: {error}\n")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
