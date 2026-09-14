"""Local Parakeet dictation prototype. Audio never goes to a server."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'skipper'
MODEL = Path(os.environ.get('SKIPPER_MODEL_DIR',
             ROOT / 'models/parakeet-tdt-0.6b-v3-int8' if (ROOT / 'models/parakeet-tdt-0.6b-v3-int8').is_dir()
             else DATA / 'models/parakeet-tdt-0.6b-v3-int8'))


def download():
    manifest = json.loads((ROOT / "model-manifest.json").read_text())
    MODEL.mkdir(parents=True, exist_ok=True)
    for entry in manifest["files"]:
        path = MODEL / entry["rfilename"]
        expected = entry.get("lfs", {}).get("sha256")

        def valid(candidate):
            if not candidate.is_file() or candidate.stat().st_size != entry["size"]:
                return False
            with candidate.open("rb") as handle:
                return not expected or hashlib.file_digest(handle, "sha256").hexdigest() == expected

        if valid(path):
            print(f"Verified {path.name}")
            continue
        url = f"https://huggingface.co/{manifest['repo']}/resolve/{manifest['revision']}/{path.name}"
        part = path.with_suffix(path.suffix + ".part")
        print(f"Downloading {path.name}...", flush=True)
        urllib.request.urlretrieve(url, part)
        if not valid(part):
            raise ValueError(f"Download verification failed: {path.name}")
        part.replace(path)


def load_model(threads):
    # Transcription must work without Hugging Face or any network service.
    os.environ["HF_HUB_OFFLINE"] = "1"
    import onnx_asr
    import onnxruntime as ort

    manifest = json.loads((ROOT / "model-manifest.json").read_text())
    if any(not (MODEL / f["rfilename"]).is_file() for f in manifest["files"]):
        raise ValueError("Model missing. Run: python skipper.py download")
    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    start = time.perf_counter()
    model = onnx_asr.load_model(
        "nemo-parakeet-tdt-0.6b-v3", MODEL, quantization="int8",
        providers=["CPUExecutionProvider"], sess_options=options,
    )
    return model, time.perf_counter() - start


def recognize_file(model, path, load_seconds=0):
    import numpy as np

    with wave.open(str(path), "rb") as audio:
        rate = audio.getframerate()
        duration = audio.getnframes() / rate
        if audio.getnchannels() != 1 or audio.getsampwidth() != 2 or rate != 16000:
            raise ValueError("Use a mono, 16-bit PCM WAV at 16000 Hz.")
        if not 0 < duration <= 30:
            raise ValueError("This prototype accepts clips up to 30 seconds.")
        samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2").astype(np.float32) / 32768
    start = time.perf_counter()
    result = model.recognize(samples, sample_rate=rate)
    elapsed = time.perf_counter() - start
    return result, {
        "audio_seconds": round(duration, 3),
        "load_seconds": round(load_seconds, 3),
        "transcribe_seconds": round(elapsed, 3),
        "times_realtime": round(duration / elapsed, 2),
        "peak_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "provider": "CPUExecutionProvider",
    }


def transcribe(model, path, load_seconds):
    result, metrics = recognize_file(model, path, load_seconds)
    print(result)
    print(json.dumps(metrics), file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threads", type=int, default=4)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("download", help="Download and verify the pinned INT8 model")
    wav = commands.add_parser("transcribe", help="Transcribe a local WAV (maximum 30 seconds)")
    wav.add_argument("wav", type=Path)
    record = commands.add_parser("record", help="Record from PipeWire, then transcribe locally")
    record.add_argument("--seconds", type=int, default=10, choices=range(1, 31), metavar="1..30")
    args = parser.parse_args()
    if not 1 <= args.threads <= 16:
        parser.error("--threads must be between 1 and 16")
    try:
        if args.command == "download":
            download()
            return
        print("Loading local Parakeet model...", file=sys.stderr, flush=True)
        model, load_seconds = load_model(args.threads)
        if args.command == "transcribe":
            transcribe(model, args.wav, load_seconds)
        else:
            with tempfile.TemporaryDirectory(prefix="skipper-") as directory:
                path = Path(directory) / "recording.wav"
                print(f"Recording for {args.seconds} seconds. Speak now.", file=sys.stderr, flush=True)
                subprocess.run([
                    "pw-record", "--rate", "16000", "--channels", "1", "--format", "s16",
                    "--sample-count", str(args.seconds * 16000), str(path),
                ], check=True, timeout=args.seconds + 15)
                transcribe(model, path, load_seconds)
    except (OSError, ValueError, wave.Error, subprocess.SubprocessError) as exc:
        parser.exit(1, f"Skipper: {exc}\n")
    except KeyboardInterrupt:
        parser.exit(130, "\nCancelled.\n")


if __name__ == "__main__":
    main()
