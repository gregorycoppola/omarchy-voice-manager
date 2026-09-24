import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import personal_store
from corrections import Corrections
from custom_actions import CustomActions
from intent_matching import IntentMatcher

class PersonalStoreTests(unittest.TestCase):
    def test_migration_retains_original_and_sqlite_becomes_authoritative(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'aliases.json'
            original = json.dumps({'version':1,'aliases':{'launch discord please':'discord'}})
            path.write_text(original)
            matcher = IntentMatcher(path)
            self.assertEqual(matcher.exact('launch discord please'), 'discord')
            matcher.forget('launch discord please')
            self.assertIsNone(IntentMatcher(path).exact('launch discord please'))
            self.assertEqual(path.read_text(), original)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_fresh_user_has_private_database_and_no_json(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with patch.object(personal_store, 'DEFAULT_DATA', root/'data'), patch.object(personal_store, 'DEFAULT_STATE', root/'state'):
                store = personal_store.initialize(root/'data')
                self.assertEqual(store.path, root/'state/command-history.sqlite3')
                self.assertEqual(store.path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(store.path.parent.stat().st_mode & 0o777, 0o700)
                self.assertFalse(list(root.rglob('*.json')))

    def test_explicit_speech_override_then_shared_then_personal_exact(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            matcher = IntentMatcher(root/'aliases.json')
            Corrections(root/'corrections.json').save('open chrome','open discord','discord')
            self.assertEqual(matcher.parse('open chrome').command,'discord')
            self.assertEqual(matcher.parse('open chrome',use_corrections=False).command,'browser')
            CustomActions(root/'actions.json').save('Quiet','quiet time','volume:mute')
            self.assertEqual(matcher.parse('quiet time').selected.source,'custom')
            self.assertIsNone(matcher.parse('quiet tyme').command)
            with self.assertRaises(ValueError):
                matcher.learn('open chrome','discord')
