# -*- coding: utf-8 -*-
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from db_client import DBClient
from config import DB_CONFIG

db = DBClient(DB_CONFIG)

# 检查股票代码300086
print("检查股票代码300086:")
rows = db.fetch_all(
    "SELECT * FROM listed_company_basic_info WHERE stock_code = %s", ("300086",)
)
if rows:
    for r in rows:
        print(f"  {r}")
else:
    print("  未找到")

# 列出所有公司
print("\n数据库所有公司:")
rows = db.fetch_all(
    "SELECT stock_code, stock_abbr FROM listed_company_basic_info ORDER BY stock_code"
)
for r in rows:
    print(f"  {r['stock_code']} - {r['stock_abbr']}")

db.close()
