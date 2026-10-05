import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from intent_dataset_bridge import IntentDatasetBridge, DATA_ROOT
from intent_dataset_aliases import load_approved_aliases
from intent_matching import IntentMatcher


class IntentDatasetBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bridge = IntentDatasetBridge()

    def test_referenced_dataset_and_synthetic_phrase(self):
        self.assertEqual(len(self.bridge.outcomes), 227)
        result = self.bridge.preview("Please open the browser.")
        self.assertEqual(result.status, "single")
        self.assertEqual(result.intent_ids, ("browser.open",))
        self.assertEqual(result.phrases[0].origin, "synthetic_frame")
        self.assertIsNone(result.source_command)

    def test_source_macro_agrees_with_current_skipper_grammar(self):
        result = self.bridge.preview("open the browser and tile")
        self.assertEqual(result.status, "sequence")
        self.assertEqual(result.intent_ids, ("browser.open", "window.tile_pair"))
        self.assertEqual(result.source_command, "browser:open_tile")
        with tempfile.TemporaryDirectory() as directory:
            actual = IntentMatcher(Path(directory) / "aliases.json").parse(result.text)
        self.assertEqual(actual.command, result.source_command)

    def test_proposed_combination_is_not_claimed_as_skipper_command(self):
        result = self.bridge.preview("open the browser and tile the windows")
        self.assertEqual(result.intent_ids, ("browser.open", "window.tile"))
        self.assertEqual(result.evidence, "proposed_combination")
        self.assertIsNone(result.source_command)

    def test_and_between_targets_stays_one_clause(self):
        result = self.bridge.preview("tile this window and the browser")
        self.assertEqual(result.status, "single")
        self.assertEqual(result.intent_ids, ("window.tile_pair",))
        self.assertEqual(IntentDatasetBridge.split_clauses(result.text), (result.text,))

    def test_unknown_sequence_exposes_clauses_without_guessing(self):
        result = self.bridge.preview("open a terminal and play music")
        self.assertEqual(result.status, "unlabeled_sequence")
        self.assertEqual(result.clauses, ("open a terminal", "play music"))
        self.assertEqual(result.intent_ids, ())

    def test_invalid_external_schema_example_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'data'
            shutil.copytree(DATA_ROOT, target)
            path = target / 'catalog.json'
            value = json.loads(path.read_text())
            row = next(x for x in value['intents'] if x['id'] == 'browser.open')
            row['examples'][0]['arguments']['presentation'] = 'unknown'
            path.write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                IntentDatasetBridge(target)

    def test_approved_dataset_phrases_reach_existing_exact_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "aliases.json"
            matcher = IntentMatcher(path)
            for phrase, command in [
                ("Could you open the browser?", "browser:open_fullscreen"),
                ("Put this window beside the browser", "windows:tile_current_browser"),
            ]:
                result = matcher.parse(phrase)
                self.assertEqual(result.command, command)
                self.assertEqual(result.method, "exact")
                self.assertEqual(result.selected.source, "dataset_approved")
            self.assertIsNone(matcher.exact("Please bring up the browser."))
            self.assertFalse(path.exists())

    def test_approved_aliases_are_explicit_and_bounded(self):
        aliases = load_approved_aliases(bridge=self.bridge)
        self.assertEqual(len(aliases), 14)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "approved.json"
            path.write_text(json.dumps({"schema_version": 2, "approved_aliases": [
                {"intent": "email.send", "variant": 1, "command": "browser:open_fullscreen"}]}))
            with self.assertRaisesRegex(ValueError, "arguments disagree"):
                load_approved_aliases(path, self.bridge)
            path.write_text(json.dumps({"schema_version": 2, "approved_aliases": [
                {"intent": "browser.open", "variant": 3, "text": "changed wording",
                 "command": "browser:open_fullscreen"}]}))
            with self.assertRaisesRegex(ValueError, "wording changed"):
                load_approved_aliases(path, self.bridge)

    def test_existing_grammar_survives_unavailable_dataset_aliases(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch("intent_matching.load_approved_aliases", side_effect=OSError("missing bundle")):
            matcher = IntentMatcher(Path(directory) / "aliases.json")
            self.assertIn("missing bundle", matcher.dataset_error)
            self.assertEqual(matcher.parse("open the browser").command, "browser:open_fullscreen")
            self.assertIsNone(matcher.exact("Could you open the browser?"))


if __name__ == "__main__":
    unittest.main()
