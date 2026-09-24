"""Load the independently maintained intent dataset through an explicit reference."""
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REFERENCE = json.loads((ROOT / "dataset-reference.json").read_text())
if REFERENCE.get("schema_version") != 2 or REFERENCE.get("provider") != "skipper":
    raise ValueError("Unsupported dataset-reference.json")
installed = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'skipper/intent-dataset'
development = ROOT / REFERENCE['path']
DATASET_ROOT = Path(os.environ.get("OMARCHY_INTENT_DATASET", development if (development / 'data/catalog.json').is_file() else installed)).expanduser().resolve()
API_PATH = DATASET_ROOT / "intent_explorer/catalog.py"
if not API_PATH.is_file():
    raise RuntimeError(
        f"Intent dataset missing at {DATASET_ROOT}. Set OMARCHY_INTENT_DATASET to the "
        "omarchy-voice-dataset checkout, or update dataset-reference.json.")
spec = importlib.util.spec_from_file_location("omarchy_intent_catalog", API_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
CATALOG = module.Catalog(DATASET_ROOT)
PROVIDER = CATALOG.providers[REFERENCE["provider"]]
DATASET_REVISION = CATALOG.revision
