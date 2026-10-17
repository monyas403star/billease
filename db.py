import sqlite3

def get_conn():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row 
    return conn

def query(sql, params=None, fetch=False, one=False):
    sql = sql.replace("%s", "?")
    
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(sql, params or ())
    result = None
    
    if fetch:
        if one:
            row = cur.fetchone()
            result = dict(row) if row else None
        else:
            rows = cur.fetchall()
            result = [dict(r) for r in rows]
    else:
        conn.commit()
        result = cur.lastrowid
        
    cur.close()
    conn.close()
    return result