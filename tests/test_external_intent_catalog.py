import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from dataset_source import CATALOG, DATASET_ROOT
from intent_matching import IntentMatcher
from window_vocabulary import inject_windows


class ExternalIntentCatalogTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.matcher = IntentMatcher(Path(directory.name) / 'aliases.json')

    def test_structured_input_uses_same_adapter_as_grammar(self):
        parsed = self.matcher.parse('open the browser')
        instance = parsed.canonical_plan[0]
        self.assertEqual(instance, {'intent': 'browser.open', 'arguments': {
            'browser': 'default', 'presentation': 'fullscreen'}})
        self.assertEqual(self.matcher.parse_instance(instance).command, parsed.command)
        instance['arguments']['browser'] = 'uninstalled-browser'
        self.assertEqual(self.matcher.parse_instance(instance).status, 'unrecognized')

    def test_live_window_ids_survive_shared_intent_binding(self):
        windows = inject_windows({'clients': [{
            'class': 'kitty', 'address': '0x123', 'stableId': 'fixture-1',
            'pid': 123, 'title': 'Dataset work | project', 'mapped': True}]})
        parsed = self.matcher.parse('focus dataset work', windows.expansions)
        target = parsed.canonical_plan[0]['arguments']['target']
        self.assertEqual(target['kind'], 'id')
        self.assertIn(target['value'], windows.targets)
        self.assertEqual(self.matcher.parse_instance(parsed.canonical_plan[0], windows.expansions).command,
                         parsed.command)

    def test_editing_external_pattern_changes_parser_without_app_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'dataset'
            shutil.copytree(DATASET_ROOT / 'data', root / 'data')
            shutil.copytree(DATASET_ROOT / 'intent_explorer', root / 'intent_explorer')
            path = root / 'data/providers/skipper.json'
            provider = json.loads(path.read_text())
            rule = next(r for r in provider['rules'] if r['id'] == 'open_browser')
            rule['patterns'].append('summon <browser>')
            path.write_text(json.dumps(provider))
            result = subprocess.run([sys.executable, '-c',
                "from intent_matching import IntentMatcher; "
                "r=IntentMatcher('/nonexistent/aliases.json').parse('summon chromium'); "
                "assert r.command == 'browser'; assert r.canonical_plan[0]['intent'] == 'browser.open'"],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, 'OMARCHY_INTENT_DATASET': str(root)}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_dataset_has_actionable_error(self):
        result = subprocess.run([sys.executable, '-c', 'import command_catalog'],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, 'OMARCHY_INTENT_DATASET': '/nonexistent/intent-dataset'},
            capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Set OMARCHY_INTENT_DATASET', result.stderr)


if __name__ == '__main__':
    unittest.main()
