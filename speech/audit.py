"""Durable request and response events independent of debugger window lifetime."""
from contextlib import closing
import sqlite3
from speech.storage import DATABASE, migrate
from speech.history import event


def append(kind,data,observation_id=None):
    migrate()
    DATABASE.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with closing(sqlite3.connect(DATABASE,timeout=10)) as db,db:
        ident=event(db,kind,data,observation_id)
    DATABASE.chmod(0o600)
    return ident
