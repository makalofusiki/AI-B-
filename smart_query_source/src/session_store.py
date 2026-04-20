from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any


class SessionStore:
    def __init__(self, db_path: str, ttl_hours: int = 24):
        self.db_path = Path(db_path)
        self.ttl_hours = ttl_hours
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self):
        return sqlite3.connect(str(self.db_path))

    def _init_db(self):
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id TEXT PRIMARY KEY,
                    context_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def get_context(self, session_id: str) -> Dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT context_json, updated_at FROM chat_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                return {}
            context_json, updated_at = row
            dt = datetime.fromisoformat(updated_at)
            if dt < datetime.utcnow() - timedelta(hours=self.ttl_hours):
                conn.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))
                conn.commit()
                return {}
            try:
                return json.loads(context_json or "{}")
            except Exception:
                return {}

    def save_context(self, session_id: str, context: Dict[str, Any]):
        now = datetime.utcnow().isoformat()
        payload = json.dumps(context, ensure_ascii=False, default=str)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO chat_sessions (session_id, context_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    context_json = excluded.context_json,
                    updated_at = excluded.updated_at
                """,
                (session_id, payload, now),
            )
            conn.commit()

    def clear(self, session_id: str):
        with self._conn() as conn:
            conn.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))
            conn.commit()
