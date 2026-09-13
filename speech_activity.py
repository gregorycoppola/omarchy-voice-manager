"""Local Silero ONNX inference and bounded speech/silence segmentation."""
from collections import deque
import hashlib
import json
from pathlib import Path
import urllib.request

import numpy as np

ROOT = Path(__file__).resolve().parent
VAD_DIR = ROOT / "models/silero-vad"
FRAME_SAMPLES = 512  # 32 ms at 16 kHz


def download_vad():
    manifest = json.loads((ROOT / "vad-manifest.json").read_text())
    VAD_DIR.mkdir(parents=True, exist_ok=True)
    for name, entry in manifest["files"].items():
        path = VAD_DIR / name
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]:
            continue
        partial = path.with_suffix(path.suffix + ".part")
        urllib.request.urlretrieve(entry["url"], partial)
        if hashlib.sha256(partial.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"VAD checksum mismatch: {name}")
        partial.replace(path)


class SpeechDetector:
    """Silero's documented 16 kHz streaming interface, CPU only, no PyTorch."""
    def __init__(self):
        import onnxruntime as ort
        path = VAD_DIR / "silero_vad.onnx"
        expected = json.loads((ROOT / "vad-manifest.json").read_text())["files"][path.name]["sha256"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Speech detector missing or damaged. Run: python speech_activity.py download")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"], sess_options=options)
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        self.context = np.zeros((1, 64), dtype=np.float32)

    def probability(self, pcm):
        if len(pcm) != FRAME_SAMPLES * 2:
            raise ValueError("VAD requires exactly 512 PCM16 samples")
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32).reshape(1, -1) / 32768
        inputs = {"input": np.concatenate((self.context, audio), axis=1),
                  "state": self.state, "sr": np.array(16000, dtype=np.int64)}
        score, self.state = self.session.run(None, inputs)
        self.context = audio[:, -64:].copy()
        return float(score.reshape(-1)[0])


class SpeechSegmenter:
    """Hysteresis: 96 ms onset, 320 ms pre-roll, 704 ms quiet endpoint.

    At least 256 ms of confident speech is required to emit a take. Every take
    is bounded to 28 seconds, leaving room within the transcription limit.
    """
    def __init__(self):
        self.pre_roll = deque(maxlen=10)
        self.frames = []
        self.onset = 0
        self.voiced = 0
        self.quiet = 0

    @property
    def active(self):
        return bool(self.frames)

    def feed(self, pcm, probability):
        if len(pcm) != FRAME_SAMPLES * 2:
            raise ValueError("Segmenter requires 512 PCM16 samples")
        if not self.active:
            self.pre_roll.append(pcm)
            self.onset = self.onset + 1 if probability >= .6 else 0
            if self.onset >= 3:
                self.frames = list(self.pre_roll)
                self.voiced = self.onset
                self.quiet = 0
            return None
        self.frames.append(pcm)
        if probability >= .6:
            self.voiced += 1
        self.quiet = self.quiet + 1 if probability < .35 else 0
        if self.quiet >= 22 or len(self.frames) >= 875:
            result = b"".join(self.frames) if self.voiced >= 8 else None
            self.frames = []
            self.pre_roll.clear()
            self.onset = self.voiced = self.quiet = 0
            return result
        return None


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["download"])
    parser.parse_args()
    download_vad()
    print("Silero VAD downloaded and verified")
