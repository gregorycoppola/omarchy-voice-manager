"""The plugin carries its own compatible dataset without an external checkout."""
from pathlib import Path
import tempfile
import os
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DatasetInstallTests(unittest.TestCase):
    def run_loader(self, app, **extra):
        env = dict(os.environ, XDG_DATA_HOME=str(app.parent/'data'))
        env.pop('OMARCHY_INTENT_DATASET', None)
        env.update(extra)
        return subprocess.run([sys.executable, '-B', '-c',
            'from dataset_source import DATASET_ROOT, CATALOG; '
            'print(DATASET_ROOT); assert CATALOG.providers["skipper"]'],
            cwd=app, env=env, text=True, capture_output=True)

    def copy_app(self, directory):
        app = Path(directory)/'app'
        app.mkdir()
        for name in ('dataset_source.py', 'dataset-reference.json'):
            shutil.copyfile(ROOT/name, app/name)
        shutil.copytree(ROOT/'bundled', app/'bundled')
        return app

    def test_bundle_loads_without_other_repositories(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self.copy_app(directory)
            # Stale installed data and a sibling checkout must not override this release.
            for stale in [Path(directory)/'data/skipper/intent-dataset',
                          Path(directory)/'omarchy-voice-dataset']:
                (stale/'data').mkdir(parents=True)
                (stale/'data/catalog.json').write_text('invalid')
            result = self.run_loader(app)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), str(app/'bundled/intents'))
            self.assertTrue((app/'bundled/intents/LICENSE').is_file())

    def test_explicit_development_override(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self.copy_app(directory)
            external = Path(directory)/'external'
            shutil.copytree(app/'bundled/intents', external)
            result = self.run_loader(app, OMARCHY_INTENT_DATASET=str(external))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), str(external))

    def test_missing_bundle_fails_with_reinstall_guidance(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self.copy_app(directory)
            shutil.rmtree(app/'bundled')
            result = self.run_loader(app)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('reinstall Skipper', result.stderr)
