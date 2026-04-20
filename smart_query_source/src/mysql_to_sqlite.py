"""
Export MySQL database to a single SQLite file.
Run from project root: python src/mysql_to_sqlite.py
"""
from __future__ import annotations

import os
import sqlite3
import pymysql
from config import DB_CONFIG


def main():
    out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    os.makedirs(out_dir, exist_ok=True)
    sqlite_path = os.path.join(out_dir, "financial_reports.sqlite")
    if os.path.exists(sqlite_path):
        os.remove(sqlite_path)

    # connect to mysql
    conn = pymysql.connect(
        host=DB_CONFIG['host'], port=DB_CONFIG['port'], user=DB_CONFIG['user'],
        password=DB_CONFIG['password'], database=DB_CONFIG['database'], charset=DB_CONFIG.get('charset','utf8mb4'),
        cursorclass=pymysql.cursors.DictCursor, autocommit=True)

    try:
        cur = conn.cursor()
        cur.execute("SELECT TABLE_NAME FROM information_schema.tables WHERE table_schema=%s", (DB_CONFIG['database'],))
        tables = [r['TABLE_NAME'] for r in cur.fetchall()]

        # create sqlite and copy data
        sconn = sqlite3.connect(sqlite_path)
        scur = sconn.cursor()

        for t in tables:
            print('Exporting', t)
            # get columns
            cur.execute(f"SHOW COLUMNS FROM `{t}`")
            cols = [r['Field'] for r in cur.fetchall()]
            # create table in sqlite with all TEXT columns
            col_defs = ", ".join([f'"{c}" TEXT' for c in cols])
            scur.execute(f'CREATE TABLE "{t}" ({col_defs})')

            # fetch all rows from mysql
            cur.execute(f"SELECT * FROM `{t}`")
            rows = cur.fetchall()
            if not rows:
                sconn.commit()
                continue
            placeholders = ','.join(['?'] * len(cols))
            insert_sql = f'INSERT INTO "{t}" ({",".join(["\""+c+"\"" for c in cols])}) VALUES ({placeholders})'
            to_insert = []
            from decimal import Decimal
            import datetime
            for r in rows:
                row_vals = []
                for c in cols:
                    v = r.get(c)
                    if v is None:
                        row_vals.append(None)
                        continue
                    if isinstance(v, Decimal):
                        # convert Decimal to float to be sqlite-compatible
                        try:
                            row_vals.append(float(v))
                        except Exception:
                            row_vals.append(str(v))
                        continue
                    if isinstance(v, (datetime.date, datetime.datetime)):
                        row_vals.append(v.isoformat())
                        continue
                    if isinstance(v, bytes):
                        try:
                            row_vals.append(v.decode('utf-8'))
                        except Exception:
                            row_vals.append(str(v))
                        continue
                    row_vals.append(v)
                to_insert.append(row_vals)
            scur.executemany(insert_sql, to_insert)
            sconn.commit()
        scur.close()
        sconn.close()
        print('SQLite export completed:', sqlite_path)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
