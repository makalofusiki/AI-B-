# -*- coding: utf-8 -*-
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import pandas as pd
import re
import json

from db_client import DBClient
from config import DB_CONFIG

# 定义中药行业公司列表（完整版）
all_tcm_companies = [
    "佐力药业",
    "千金药业",
    "康美药业",
    "振东制药",
    "新天药业",
    "香雪制药",
    "康芝药业",
    "方盛制药",
    "以岭药业",
    "太极集团",
    "健民集团",
    "云南白药",
    "华润三九",
    "片仔癀",
    "东阿阿胶",
    "九芝堂",
    "沃华医药",
    "吉林敖东",
    "步长制药",
    "金花股份",
    "仁和药业",
    "启迪药业",
    "通化金马",
    "华神科技",
    "万邦德",
    "江中药业",
    "羚锐制药",
    "马应龙",
    "桂林三金",
    "嘉应制药",
    "莱茵生物",
    "紫鑫药业",
    "益佰制药",
    "汉森制药",
    "天圣制药",
    "贵州百灵",
    "盘龙药业",
    "新光药业",
    "佛慈制药",
    "陇神戎发",
    "康弘药业",
    "信邦制药",
    "恩威制药",
    "神奇制药",
    "太安堂",
    "上海凯宝",
    "红日药业",
    "中恒集团",
    "益盛药业",
    "龙津药业",
    "大理药业",
    "众生药业",
    "科伦药业",
    "福安药业",
    "尔康制药",
    "山河药辅",
    "黄山胶囊",
    "仟源医药",
    "昂利康",
    "东亚药业",
    "亨迪药业",
    "华纳药厂",
    "之江生物",
    "赛隆药业",
    "太龙药业",
    "康惠制药",
    "维和药业",
    "三力制药",
    "威门药业",
    "锦波生物",
]

# 读取所有问题
all_questions = []
for f in [
    r"D:\BaiduNetdiskDownload\data\附件4：问题汇总.xlsx",
    r"D:\BaiduNetdiskDownload\data\附件6：问题汇总.xlsx",
]:
    df = pd.read_excel(f)
    for idx, row in df.iterrows():
        qid = str(row.get("编号", ""))
        qtext = str(row.get("问题", ""))
        if qid and qtext and qid != "nan":
            all_questions.append({"id": qid, "text": qtext})

print(f"总问题数: {len(all_questions)}")

# 在问题中搜索公司名
mentioned = {}
for q in all_questions:
    text = q["text"]
    for c in all_tcm_companies:
        if c in text:
            if c not in mentioned:
                mentioned[c] = {"count": 0, "questions": []}
            mentioned[c]["count"] += 1
            mentioned[c]["questions"].append(q["id"])

print(f"\n问题中明确提到的公司: {len(mentioned)}")
for c, info in sorted(mentioned.items(), key=lambda x: -x[1]["count"]):
    print(f"  {c}: {info['count']}次 (问题: {info['questions']})")

# 连接数据库
db = DBClient(DB_CONFIG)
db_companies = {}
rows = db.fetch_all(
    "SELECT stock_code, stock_abbr, company_name FROM listed_company_basic_info"
)
for r in rows:
    code = str(r["stock_code"]).zfill(6)
    db_companies[code] = r["stock_abbr"]
    db_companies[r["stock_abbr"]] = code
db.close()

print(f"\n数据库公司数: {len(rows)}")

# 分类
in_db = []
not_in_db = []
for c in mentioned:
    if c in db_companies:
        in_db.append(c)
    else:
        not_in_db.append(c)

print(f"\n{'=' * 60}")
print("缺失公司汇总")
print("=" * 60)
print(f"问题中提到且在数据库中: {len(in_db)}")
print(f"  {sorted(in_db)}")
print(f"\n问题中提到但不在数据库中: {len(not_in_db)}")
print(f"  {sorted(not_in_db)}")

# 缺失公司的股票代码
print(f"\n{'=' * 60}")
print("缺失公司的股票代码参考")
print("=" * 60)
missing_codes = {
    "康美药业": "600518",
    "振东制药": "300158",
    "新天药业": "002873",
    "康芝药业": "300086",
    "方盛制药": "603998",
    "以岭药业": "002603",
    "吉林敖东": "000623",
    "江中药业": "600750",
    "羚锐制药": "600285",
    "马应龙": "600993",
    "桂林三金": "002275",
    "莱茵生物": "002166",
    "紫鑫药业": "002118",
    "益佰制药": "600594",
    "汉森制药": "002412",
    "贵州百灵": "002424",
    "佛慈制药": "002644",
    "康弘药业": "002773",
    "太安堂": "002433",
    "上海凯宝": "300039",
    "红日药业": "300026",
    "龙津药业": "002750",
    "大理药业": "603963",
    "众生药业": "002317",
    "仟源医药": "300254",
    "赛隆药业": "002898",
    "太龙药业": "600222",
    "康惠制药": "603139",
    "三力制药": "835323",
    "威门药业": "430369",
}

for c in sorted(not_in_db):
    code = missing_codes.get(c, "未知")
    print(f"  {c}: {code}")
