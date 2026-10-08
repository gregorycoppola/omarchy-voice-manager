"""Local model location shared by setup, runtime, and speech worker launcher."""
import json
import os
import tempfile
from pathlib import Path
from speech.storage import CONFIG, DATA

MODEL_FILES=('config.json','encoder-model.int8.onnx','decoder_joint-model.int8.onnx','vocab.txt')

def model_path():
    if os.environ.get('SKIPPER_PARAKEET_MODEL'):
        return Path(os.environ['SKIPPER_PARAKEET_MODEL']).expanduser()
    config=CONFIG/'voice.json'
    if config.is_file():
        return Path(json.loads(config.read_text())['model_path']).expanduser()
    own=DATA/'models/parakeet-tdt-0.6b-v3-int8'
    if own.is_dir():return own
    return Path.home()/'.local/share/voxtype/models/parakeet-tdt-0.6b-v3-int8'

def configure_model(path):
    path=Path(path).expanduser().resolve()
    missing=[name for name in MODEL_FILES if not (path/name).is_file()]
    if missing:raise ValueError('Model files missing: '+', '.join(missing))
    CONFIG.mkdir(parents=True,exist_ok=True,mode=0o700)
    with tempfile.NamedTemporaryFile(mode='w',dir=CONFIG,delete=False) as output:
        json.dump({'model_path':str(path)},output)
    os.replace(output.name,CONFIG/'voice.json')
    return path
