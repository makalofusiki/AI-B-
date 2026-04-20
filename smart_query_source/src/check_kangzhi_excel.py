# -*- coding: utf-8 -*-
import pandas as pd
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# 读取个股研报信息Excel
try:
    df = pd.read_excel(
        r"D:\BaiduNetdiskDownload\data\附件5：研报数据\个股_研报信息.xlsx"
    )
    print("个股研报信息表列名:")
    print(df.columns.tolist())
    print(f"\n总行数: {len(df)}")

    # 搜索康芝药业
    print("\n搜索康芝药业...")
    mask = (
        df.astype(str)
        .apply(lambda x: x.str.contains("康芝|300086", na=False))
        .any(axis=1)
    )
    kangzhi_rows = df[mask]

    print(f"找到 {len(kangzhi_rows)} 条康芝药业相关记录")
    if len(kangzhi_rows) > 0:
        print("\n康芝药业相关记录:")
        for idx, row in kangzhi_rows.iterrows():
            print(f"\n记录 {idx}:")
            for col in df.columns:
                val = row.get(col)
                if pd.notna(val) and str(val).strip():
                    print(f"  {col}: {val}")

except Exception as e:
    print(f"错误: {e}")
    import traceback

    traceback.print_exc()
