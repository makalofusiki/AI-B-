# -*- coding: utf-8 -*-
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import pandas as pd
from db_client import DBClient
from config import DB_CONFIG

# 检查康芝药业的数据情况
db = DBClient(DB_CONFIG)

# 检查各表中是否有康芝药业的数据
tables = [
    "income_sheet",
    "balance_sheet",
    "cash_flow_sheet",
    "core_performance_indicators_sheet",
]
print("=" * 60)
print("康芝药业(300086)数据检查")
print("=" * 60)

for t in tables:
    rows = db.fetch_all(
        f"SELECT COUNT(*) as cnt FROM {t} WHERE stock_code = %s", ("300086",)
    )
    print(f"{t}: {rows[0]['cnt']} 条记录")

# 检查问题中提到的具体问题
print("\n" + "=" * 60)
print("问题B2061 - 完整问题内容")
print("=" * 60)

# 读取问题文件
df = pd.read_excel(r"D:\BaiduNetdiskDownload\data\附件6：问题汇总.xlsx")
for idx, row in df.iterrows():
    if str(row.get("编号", "")) == "B2061":
        print(f"问题: {row['问题']}")
        break

# 检查其他缺失公司
print("\n" + "=" * 60)
print("其他公司数据情况")
print("=" * 60)

# 康芝药业相关公司对比
codes_to_check = ["300086", "300181", "002566", "002737", "002773"]
for code in codes_to_check:
    for t in ["income_sheet"]:
        rows = db.fetch_all(
            f"SELECT COUNT(*) as cnt FROM {t} WHERE stock_code = %s", (code,)
        )
        print(f"{code} - {t}: {rows[0]['cnt']} 条记录")
        break

db.close()
