"""Load the independently maintained intent dataset through an explicit reference."""
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REFERENCE = json.loads((ROOT / "dataset-reference.json").read_text())
if REFERENCE.get("schema_version") != 3 or REFERENCE.get("provider") != "skipper":
    raise ValueError("Unsupported dataset-reference.json")
# Overrides are deliberate. Never discover sibling repositories or stale installed copies.
DATASET_ROOT = Path(os.environ.get(
    "OMARCHY_INTENT_DATASET", ROOT / REFERENCE['bundle'])).expanduser().resolve()
API_PATH = DATASET_ROOT / "intent_explorer/catalog.py"
if not API_PATH.is_file():
    raise RuntimeError(
        f"Intent dataset missing at {DATASET_ROOT}. Set OMARCHY_INTENT_DATASET to the "
        "omarchy-voice-dataset checkout, or reinstall Skipper to restore its bundled intents.")
spec = importlib.util.spec_from_file_location("omarchy_intent_catalog", API_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
CATALOG = module.Catalog(DATASET_ROOT)
PROVIDER = CATALOG.providers[REFERENCE["provider"]]
DATASET_REVISION = CATALOG.revision
