#!/usr/bin/env python3
"""
从数据库运行全量问题处理
"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.getcwd(), 'src'))
from config import DB_CONFIG, RESULT_DIR
from db_client import DBClient
from query_engine import QueryEngine

def main():
    db = DBClient(DB_CONFIG)
    engine = QueryEngine(db, RESULT_DIR)
    
    # 从数据库获取所有问题
    cursor = db.conn.cursor()
    cursor.execute("SELECT question_code, question_type, question_content, sub_questions FROM questions")
    rows = cursor.fetchall()
    
    print(f"找到 {len(rows)} 个问题")
    
    os.makedirs(RESULT_DIR, exist_ok=True)
    
    for qid, qtype, qraw, sub_q in rows:
        print(f"处理: {qid}...")
        
        # 解析问题
        import json
        q_list = []
        if sub_q:
            try:
                sub_q_data = json.loads(sub_q)
                q_list = [str(x.get("Q", "")).strip() for x in sub_q_data if str(x.get("Q", "")).strip()]
            except:
                pass
        if not q_list and qraw:
            q_list = [str(qraw)]
        
        if not q_list:
            continue
            
        context = {}
        turn_answers = []
        
        for idx, q_text in enumerate(q_list, start=1):
            ans = engine.answer(qid, q_text, context=context, turn_index=idx)
            turn_answers.append(ans)
            if ans.get("context_update"):
                context.update(ans["context_update"])
        
        final_answer = turn_answers[-1] if turn_answers else {}
        
        # 保存JSON结果
        json_path = os.path.join(RESULT_DIR, f"{qid}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({
                "question_id": qid,
                "question_type": qtype,
                "turns": q_list,
                "turn_answers": turn_answers,
                "final_answer": final_answer,
            }, f, ensure_ascii=False, indent=2, default=str)
        
        print(f"  完成: {qid}")
    
    db.close()
    print("完成!")

if __name__ == '__main__':
    main()