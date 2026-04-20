import tempfile
import os
import sqlite3
from src.db_client import DBClient


def test_dbclient_sqlite_fetch_and_execute():
    fd, path = tempfile.mkstemp(suffix='.sqlite')
    os.close(fd)
    try:
        conn = sqlite3.connect(path)
        conn.execute('CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)')
        conn.execute("INSERT INTO t (name) VALUES ('Alice')")
        conn.commit()
        conn.close()

        db = DBClient({"sqlite_path": path})
        rows = db.fetch_all('SELECT * FROM t')
        assert rows[0]['name'] == 'Alice'
        rc = db.execute('INSERT INTO t (name) VALUES (?)', ('Bob',))
        # execute returns rowcount; for sqlite it's usually 1
        assert isinstance(rc, int)
        rows2 = db.fetch_all('SELECT name FROM t ORDER BY id')
        assert rows2[0]['name'] == 'Alice'
        assert rows2[1]['name'] == 'Bob'
        db.close()
    finally:
        os.remove(path)
