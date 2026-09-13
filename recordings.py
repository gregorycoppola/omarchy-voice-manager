"""Durable local recording pairs, shared by the GUI and its tests."""
from datetime import datetime
import json
from pathlib import Path
from uuid import uuid4

from keety import recognize_file


def new_recording(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    name = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + "_" + uuid4().hex[:8]
    path = directory / (name + ".wav")
    # Reserve a unique private filename before starting PipeWire.
    path.touch(mode=0o600, exist_ok=False)
    return path


def save_transcript(model, path):
    path = Path(path)
    text, metrics = recognize_file(model, path)
    for suffix, content in [(".txt", text + "\n"),
                            (".json", json.dumps(metrics, indent=2) + "\n")]:
        target = path.with_suffix(suffix)
        temporary = target.with_suffix(suffix + ".tmp")
        temporary.write_text(content)
        temporary.chmod(0o600)
        temporary.replace(target)
    return text, metrics
