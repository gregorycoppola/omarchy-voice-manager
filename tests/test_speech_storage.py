from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from speech import storage, history


class StorageTests(unittest.TestCase):
    def test_migration_preserves_sources_reviews_and_audio_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory);legacy=state/'voice-preview';legacy.mkdir()
            audio=legacy/'one.wav';audio.write_bytes(b'recording')
            original={'id':'one','source':'microphone','audio':str(audio),'parsed':{'transcript':'hello','candidates':[]}}
            with closing(sqlite3.connect(legacy/'observations.sqlite3')) as db,db:
                db.execute('CREATE TABLE observations(id TEXT PRIMARY KEY,created TEXT,data TEXT,review TEXT,intended TEXT)')
                db.execute('INSERT INTO observations VALUES(?,?,?,?,?)',('one','yesterday',json.dumps(original),'incorrect','volume up'))
            target=storage.migrate(state)
            with closing(sqlite3.connect(target)) as db:
                record=db.execute('SELECT data,review,intended FROM observations').fetchone()
                self.assertEqual(record[1:],('incorrect','volume up'))
                self.assertEqual(json.loads(record[0])['audio'],str(state/'recordings/one.wav'))
                history.initialize(db);history.initialize(db)
                self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0],1)
            with closing(sqlite3.connect(legacy/'observations.sqlite3')) as db:
                self.assertEqual(json.loads(db.execute('SELECT data FROM observations').fetchone()[0]),original)
            self.assertEqual(audio.read_bytes(),(state/'recordings/one.wav').read_bytes())
            self.assertEqual(storage.migrate(state),target)
            self.assertEqual(len(list((state/'backups').glob('*/migration.json'))),1)

    def test_save_retains_transitions_without_importing_new_records_as_legacy(self):
        with closing(sqlite3.connect(':memory:')) as db:
            db.execute('CREATE TABLE observations(id TEXT PRIMARY KEY,created TEXT,data TEXT,review TEXT,intended TEXT)')
            for status in ('pending','matched'):
                history.save(db,{'id':'a','source':'typed','parsed':{'status':status,'transcript':'hello','candidates':[]}})
            history.initialize(db)
            events=db.execute('SELECT kind,data FROM events ORDER BY sequence').fetchall()
            self.assertEqual([x[0] for x in events],['observation_saved']*2)
            self.assertEqual([json.loads(x[1])['parsed']['status'] for x in events],['pending','matched'])
