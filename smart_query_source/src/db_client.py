from __future__ import annotations

import pymysql
import sqlite3
import os
from typing import Any, Dict, Optional


class DBClient:
    def __init__(self, config: dict):
        """Init DB client. Supports MySQL (default) and SQLite when config contains 'sqlite_path'.
        For SQLite, set config['sqlite_path'] to the sqlite file path.
        """
        self.is_sqlite = False
        sqlite_path = config.get("sqlite_path") if isinstance(config, dict) else None
        if sqlite_path:
            sqlite_path = os.path.abspath(sqlite_path)
            if os.path.exists(sqlite_path):
                self.conn = sqlite3.connect(sqlite_path, check_same_thread=False)
                self.conn.row_factory = sqlite3.Row
                # register helper SQL functions to improve compatibility with MySQL-style queries
                try:
                    def _lpad(s, width, pad):
                        s = '' if s is None else str(s)
                        try:
                            w = int(width)
                        except Exception:
                            w = 0
                        padc = str(pad) if pad is not None else ' '
                        if len(padc) == 0:
                            padc = ' '
                        if len(s) >= w:
                            return s
                        return padc * max(0, w - len(s)) + s

                    def _concat(a, b, c):
                        a = '' if a is None else str(a)
                        b = '' if b is None else str(b)
                        c = '' if c is None else str(c)
                        return a + b + c

                    def _char_length(s):
                        if s is None:
                            return 0
                        return len(str(s))

                    def _field(a, b, c, d, e):
                        # emulate MySQL FIELD(arg, val1, val2, ...)
                        try:
                            seq = [b, c, d, e]
                            a_s = '' if a is None else str(a)
                            for idx, v in enumerate(seq, start=1):
                                if a_s == ('' if v is None else str(v)):
                                    return idx
                            return 0
                        except Exception:
                            return 0

                    self.conn.create_function('LPAD', 3, _lpad)
                    self.conn.create_function('CONCAT', 3, _concat)
                    self.conn.create_function('CHAR_LENGTH', 1, _char_length)
                    self.conn.create_function('FIELD', 5, _field)
                except Exception:
                    pass
                self.is_sqlite = True
                return
        # fallback to MySQL
        self.conn = pymysql.connect(
            host=config["host"],
            port=config["port"],
            user=config["user"],
            password=config["password"],
            database=config["database"],
            charset=config.get("charset", "utf8mb4"),
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )

    def _convert_placeholders(self, sql: str) -> str:
        # convert MySQL %s placeholders to sqlite ? placeholders (simple replacement)
        return sql.replace("%s", "?")

    def _run_explain(self, sql: str, params=None) -> tuple[bool, str]:
        try:
            if self.is_sqlite:
                sql2 = self._convert_placeholders(sql)
                cur = self.conn.cursor()
                cur.execute("EXPLAIN QUERY PLAN " + sql2, params or ())
                _ = cur.fetchall()
            else:
                with self.conn.cursor() as cur:
                    cur.execute("EXPLAIN " + sql, params or ())
                    _ = cur.fetchall()
            return True, ""
        except Exception as e:
            return False, str(e)

    def fetch_all(self, sql: str, params=None):
        ok, err = self._run_explain(sql, params)
        if not ok:
            raise Exception(f"SQL validation failed: {err}")
        if self.is_sqlite:
            sql2 = self._convert_placeholders(sql)
            cur = self.conn.cursor()
            cur.execute(sql2, params or ())
            rows = cur.fetchall()
            # sqlite3.Row -> dict
            return [dict(r) for r in rows]
        else:
            with self.conn.cursor() as cur:
                cur.execute(sql, params or ())
                return cur.fetchall()

    def fetch_one(self, sql: str, params=None):
        ok, err = self._run_explain(sql, params)
        if not ok:
            raise Exception(f"SQL validation failed: {err}")
        if self.is_sqlite:
            sql2 = self._convert_placeholders(sql)
            cur = self.conn.cursor()
            cur.execute(sql2, params or ())
            row = cur.fetchone()
            return dict(row) if row is not None else None
        else:
            with self.conn.cursor() as cur:
                cur.execute(sql, params or ())
                return cur.fetchone()

    def execute(self, sql: str, params=None) -> int:
        """Execute a write query and return affected rowcount."""
        ok, err = self._run_explain(sql, params)
        if not ok:
            raise Exception(f"SQL validation failed: {err}")
        if self.is_sqlite:
            sql2 = self._convert_placeholders(sql)
            cur = self.conn.cursor()
            cur.execute(sql2, params or ())
            self.conn.commit()
            return cur.rowcount
        else:
            with self.conn.cursor() as cur:
                cur.execute(sql, params or ())
                return cur.rowcount

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass
