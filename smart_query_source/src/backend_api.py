from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Any
from urllib.parse import urlparse

from batch_runner import run_batch
from config import DB_CONFIG, RESULT_DIR
from db_client import DBClient
from query_engine import QueryEngine
from session_store import SessionStore


SESSION_DB = r"D:\BaiduNetdiskDownload\data\smart_query_assistant\logs\session_store.sqlite"


def process_chat(
    question: str,
    session_id: str,
    question_id: str = "CHAT",
    turn_index: int = 1,
    session_store: SessionStore | None = None,
) -> Dict[str, Any]:
    db = DBClient(DB_CONFIG)
    try:
        engine = QueryEngine(db, RESULT_DIR)
        context = session_store.get_context(session_id) if session_store else {}
        answer = engine.answer(question_id, question, context=context, turn_index=turn_index)
        if session_store and answer.get("context_update"):
            context.update(answer["context_update"])
            session_store.save_context(session_id, context)
        return {
            "session_id": session_id,
            "question_id": question_id,
            "answer": answer,
        }
    finally:
        db.close()


class AppHandler(BaseHTTPRequestHandler):
    session_store = SessionStore(SESSION_DB)

    def _json(self, code: int, data: Dict[str, Any]):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/health":
            self._json(200, {"status": "ok"})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        p = urlparse(self.path).path
        raw_len = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(raw_len) if raw_len > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            self._json(400, {"error": "invalid json"})
            return

        if p == "/chat":
            question = str(payload.get("question", "")).strip()
            if not question:
                self._json(400, {"error": "question required"})
                return
            session_id = str(payload.get("session_id", "default"))
            question_id = str(payload.get("question_id", "CHAT"))
            turn_index = int(payload.get("turn_index", 1))
            result = process_chat(
                question=question,
                session_id=session_id,
                question_id=question_id,
                turn_index=turn_index,
                session_store=self.session_store,
            )
            self._json(200, result)
            return

        if p == "/session/clear":
            session_id = str(payload.get("session_id", "")).strip()
            if not session_id:
                self._json(400, {"error": "session_id required"})
                return
            self.session_store.clear(session_id)
            self._json(200, {"status": "cleared", "session_id": session_id})
            return

        if p == "/batch":
            input_files = payload.get("input_files") or [
                r"D:\BaiduNetdiskDownload\data\附件4：问题汇总.xlsx",
                r"D:\BaiduNetdiskDownload\data\附件6：问题汇总.xlsx",
            ]
            output_xlsx = payload.get("output_xlsx") or r"D:\BaiduNetdiskDownload\data\smart_query_assistant\result\result_2.xlsx"
            result_dir = payload.get("result_dir") or RESULT_DIR
            os.makedirs(result_dir, exist_ok=True)
            run_batch(input_files=input_files, output_xlsx=output_xlsx, result_dir=result_dir)
            self._json(200, {"status": "ok", "output_xlsx": output_xlsx, "result_dir": result_dir})
            return

        self._json(404, {"error": "not found"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    print(f"api server listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
