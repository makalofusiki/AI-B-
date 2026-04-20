from __future__ import annotations

import json

from config import DB_CONFIG, RESULT_DIR
from db_client import DBClient
from query_engine import QueryEngine


def main():
    db = DBClient(DB_CONFIG)
    engine = QueryEngine(db, RESULT_DIR)
    context = {}
    turn = 0
    qid = "CHAT"

    print("多轮问答已启动，输入 exit 退出。")
    try:
        while True:
            q = input("你: ").strip()
            if not q:
                continue
            if q.lower() in {"exit", "quit"}:
                break
            turn += 1
            ans = engine.answer(qid, q, context=context, turn_index=turn)
            if ans.get("context_update"):
                context.update(ans["context_update"])
            print("助手:")
            print(json.dumps(ans, ensure_ascii=False, indent=2, default=str))
    finally:
        db.close()


if __name__ == "__main__":
    main()
