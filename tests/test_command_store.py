import json
from pathlib import Path
import stat
import tempfile
import unittest
from command_store import CommandStore

class CommandStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'state/command-history.sqlite3'
        self.store = CommandStore(self.path)

    def test_every_use_persisted_but_recall_is_distinct_and_recent(self):
        self.store.record('Tile terminals', 'tile_terminals', 'written')
        self.store.record('tile browsers', 'tile_browsers', 'speech')
        self.store.record(' tile terminals ', 'tile_terminals', 'written')
        reloaded = CommandStore(self.path)
        self.assertEqual(reloaded.recent(), ['tile terminals', 'tile browsers'])
        with reloaded.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM commands').fetchone()[0], 3)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)

    def test_import_is_once_and_ignores_invalid_or_unrecognized(self):
        log = self.root / 'commands.jsonl'
        log.write_text('\n'.join(map(json.dumps, [
            {'event':'parsed', 'written':'tile browsers', 'command':'tile_browsers'},
            {'event':'parsed', 'written':'nonsense', 'command':None}, 42])) + '\n{broken')
        self.store.import_log(log)
        self.store.record('tile terminals', 'tile_terminals', 'written')
        self.store.import_log(log)
        self.assertEqual(self.store.recent(), ['tile terminals', 'tile browsers'])
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM commands').fetchone()[0], 2)

    def test_reject_checkout(self):
        repo = self.root / 'repo'
        (repo / '.git').mkdir(parents=True)
        with self.assertRaises(ValueError):
            CommandStore(repo / 'history.sqlite3')
