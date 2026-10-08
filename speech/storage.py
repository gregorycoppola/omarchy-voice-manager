"""Per-user XDG storage and non-destructive migration of the debugger trial."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3


def xdg(name, default):
    value=os.environ.get(name)
    return Path(value) if value and Path(value).is_absolute() else Path.home()/default


STATE=xdg('XDG_STATE_HOME','.local/state')/'skipper'
DATA=xdg('XDG_DATA_HOME','.local/share')/'skipper'
CONFIG=xdg('XDG_CONFIG_HOME','.config')/'skipper'
DATABASE=STATE/'history.sqlite3'
RECORDINGS=STATE/'recordings'
GRAMMAR=DATA/'grammar'/'current.json'


def migrate(state=STATE):
    """Copy legacy records once, preserving the source and an SQLite backup."""
    state.mkdir(parents=True,exist_ok=True,mode=0o700)
    legacy=state/'voice-preview';source=legacy/'observations.sqlite3';target=state/'history.sqlite3'
    if target.exists() or not source.exists():return target
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup=state/'backups'/('voice-preview-'+stamp);backup.mkdir(parents=True,mode=0o700)
    with closing(sqlite3.connect(source)) as old,closing(sqlite3.connect(backup/'observations.sqlite3')) as saved:
        old.backup(saved)
    pending=state/'history.sqlite3.importing'
    if pending.exists():pending.unlink()
    shutil.copy2(backup/'observations.sqlite3',pending)
    recordings=state/'recordings';recordings.mkdir(exist_ok=True,mode=0o700)
    copied=[]
    for path in legacy.iterdir():
        if path.suffix not in ('.wav','.pcm'):continue
        dest=recordings/path.name
        if dest.exists() and dest.read_bytes()!=path.read_bytes():
            raise ValueError('Recording destination conflicts: '+str(dest))
        if not dest.exists():shutil.copy2(path,dest)
        dest.chmod(0o600)
        copied.append({'source':str(path),'destination':str(dest),'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()})
    with closing(sqlite3.connect(pending)) as db,db:
        for ident,raw in db.execute('SELECT id,data FROM observations').fetchall():
            record=json.loads(raw)
            for key in ('audio','raw_audio'):
                if record.get(key) and Path(record[key]).parent==legacy:
                    dest=recordings/Path(record[key]).name
                    if dest.exists():record[key]=str(dest)
            if isinstance(record.get('input'),dict) and record.get('audio'):
                record['input']['audio']=record['audio']
            db.execute('UPDATE observations SET data=? WHERE id=?',(json.dumps(record),ident))
        count=db.execute('SELECT count(*) FROM observations').fetchone()[0]
    pending.chmod(0o600)
    pending.replace(target)
    manifest={'created':stamp,'database_source':str(source),'database_destination':str(target),
              'backup':str(backup/'observations.sqlite3'),'observations':count,'files':copied,
              'source_preserved':True}
    (backup/'migration.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return target
