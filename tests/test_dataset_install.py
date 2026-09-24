from pathlib import Path
import tempfile
import os
import shutil
import subprocess
import sys
import unittest
from plugin_setup import install_dataset
from dataset_source import DATASET_ROOT, DATASET_REVISION

class DatasetInstallTests(unittest.TestCase):
    def test_fresh_install_and_preserved_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            data = Path(d)
            self.assertEqual(install_dataset(DATASET_ROOT,data), DATASET_REVISION)
            target = data/'skipper/intent-dataset'
            self.assertTrue((target/'data/providers/skipper.json').exists())
            self.assertFalse((target/'.git').exists())
            app = data/'application'
            app.mkdir()
            for name in ('dataset_source.py','dataset-reference.json'):
                shutil.copyfile(Path(__file__).resolve().parents[1]/name,app/name)
            env = dict(os.environ, XDG_DATA_HOME=str(data))
            env.pop('OMARCHY_INTENT_DATASET',None)
            result = subprocess.run([sys.executable,'-c',
                "from dataset_source import DATASET_ROOT; print(DATASET_ROOT)"],cwd=app,env=env,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout.strip(),str(target))
            self.assertEqual((target/'installed-revision.txt').read_text().strip(), DATASET_REVISION)
            install_dataset(DATASET_ROOT,data)
            self.assertTrue(target.with_name('intent-dataset.previous').exists())
            with self.assertRaises(RuntimeError):
                install_dataset(DATASET_ROOT,data)
