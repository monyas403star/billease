import os
import sqlite3
from pathlib import Path


def database_path():
    # Default preserves the current installation. Set this only after migrating
    # the existing database to durable storage.
    return os.environ.get('BILLEASE_DB_PATH', '').strip() or 'database.db'


def get_conn():
    path = database_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def query(sql, params=None, fetch=False, one=False):
    conn = get_conn()
    try:
        with conn:
            cur = conn.execute(sql.replace('%s', '?'), params or ())
            if fetch:
                if one:
                    row = cur.fetchone()
                    return dict(row) if row else None
                return [dict(row) for row in cur.fetchall()]
            return cur.lastrowid
    finally:
        conn.close()
