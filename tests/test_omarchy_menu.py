import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from runtime import VoiceRuntime
from ui_commands import OMARCHY_MENU_FORMS

class OmarchyMenuTests(unittest.TestCase):
    def test_exact_phrases_open_main_menu_and_close_picker(self):
        for phrase in OMARCHY_MENU_FORMS:
            with self.subTest(phrase=phrase), tempfile.TemporaryDirectory() as folder:
                app=VoiceRuntime(data=Path(folder),status_path=Path(folder)/'status.json')
                app.pending_written={'token':'test'}
                with patch.object(app,'complete'), patch('runtime.subprocess.Popen') as launch:
                    app.submit_written(json.dumps({'token':'test','text':phrase}))
                launch.assert_called_once_with(['omarchy-menu','toggle','root'])
                self.assertIsNone(app.pending_written)
                self.assertIsNone(app.state['written_entry'])
