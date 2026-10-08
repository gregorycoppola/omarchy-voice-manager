"""Local debugger observations and a read-only JSONL export for offline review."""
import argparse
import json
from pathlib import Path
import sqlite3

from speech.storage import DATABASE


def normalized(observation):
    """Expose the same review fields for old and new records without reparsing."""
    record = dict(observation)
    parsed = record.get('parsed') or {}
    record['schema_version'] = 1
    record['input'] = {'source': record['source'], 'text': parsed.get('transcript'),
                       'audio': record.get('audio')}
    record['intents'] = [
        {key: candidate[key] for key in ('intent', 'canonical_plan', 'interaction',
          'launch_options', 'argument_sources', 'resolved_workspace') if key in candidate}
        for candidate in parsed.get('candidates', [])]
    if record.get('llm',{}).get('parsed'):
        record['fallback_intents']=record['llm']['parsed']['candidates']
    record.setdefault('outcome', {'status': parsed.get('status', 'pending'),
                                  'execution': 'not_executed'})
    return record


def save(db, observation):
    """Keep original creation time and reviews when an in-flight attempt advances."""
    record = normalized(observation)
    with db:
        event(db,'observation_saved',record,record['id'])
        db.execute('''INSERT INTO observations VALUES(?,datetime('now'),?,NULL,NULL)
                      ON CONFLICT(id) DO UPDATE SET data=excluded.data''',
                   (record['id'], json.dumps(record)))
    return record


def ensure_events(db):
    db.execute('CREATE TABLE IF NOT EXISTS events(sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL, created TEXT NOT NULL, observation_id TEXT, kind TEXT NOT NULL, data TEXT NOT NULL)')


def event(db,kind,data,observation_id=None,event_id=None):
    from datetime import datetime, timezone
    import uuid
    ensure_events(db)
    ident=event_id or uuid.uuid4().hex
    db.execute('INSERT OR IGNORE INTO events(id,created,observation_id,kind,data) VALUES(?,?,?,?,?)',
        (ident,datetime.now(timezone.utc).isoformat(),observation_id,kind,json.dumps(data)))
    return ident


def initialize(db):
    with db:
        ensure_events(db)
        for ident,created,data,review,intended in db.execute('SELECT id,created,data,review,intended FROM observations').fetchall():
            if db.execute('SELECT 1 FROM events WHERE observation_id=? LIMIT 1',(ident,)).fetchone():continue
            event(db,'legacy_observation_imported',{'original_created':created,'observation':json.loads(data),
                  'review':review,'intended':intended,'limitation':'Earlier transitions were not retained.'},
                  ident,'legacy:'+ident)


def rows(db):
    for ident, created, data, review, intended in db.execute(
            'SELECT id,created,data,review,intended FROM observations ORDER BY rowid'):
        record = normalized(json.loads(data))
        record.update(id=ident, created=created, review=review, intended=intended)
        yield record


def recover(db):
    """A previous process may have stopped between capture and completion."""
    for record in list(rows(db)):
        if record.get('outcome', {}).get('status') in ('recording', 'transcribing', 'parsing', 'checking_openai'):
            record['outcome'] = {'status': 'interrupted', 'execution': 'not_executed',
                                 'error': 'Debugger stopped before this attempt finished.'}
            if record.get('llm',{}).get('status')=='pending':record['llm']['status']='interrupted'
            save(db, record)


def main():
    parser = argparse.ArgumentParser(description='Export debugger history as JSONL; never reparse or execute.')
    parser.add_argument('--events',action='store_true',help='Export the append-only event timeline')
    parser.add_argument('--database', type=Path, default=DATABASE)
    args = parser.parse_args()
    with sqlite3.connect(args.database.resolve().as_uri() + '?mode=ro', uri=True) as db:
        if args.events:
            for seq,ident,created,observation_id,kind,data in db.execute('SELECT sequence,id,created,observation_id,kind,data FROM events ORDER BY sequence'):
                print(json.dumps(dict(sequence=seq,id=ident,created=created,observation_id=observation_id,kind=kind,data=json.loads(data)),ensure_ascii=False))
        else:
            for record in rows(db):
                print(json.dumps(record, ensure_ascii=False))


if __name__ == '__main__':
    main()
