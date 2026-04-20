from __future__ import annotations

import argparse
import json

from config import DB_CONFIG, RESULT_DIR
from db_client import DBClient
from query_engine import QueryEngine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--question-id", required=True, help="如 B1001")
    parser.add_argument("--question", required=True, help="自然语言问题")
    args = parser.parse_args()

    db = DBClient(DB_CONFIG)
    try:
        engine = QueryEngine(db, RESULT_DIR)
        answer = engine.answer(args.question_id, args.question)
        print(json.dumps(answer, ensure_ascii=False, indent=2, default=str))
    finally:
        db.close()


if __name__ == "__main__":
    main()
