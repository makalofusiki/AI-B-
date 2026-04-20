# -*- coding: utf-8 -*-
import os
import pdfplumber

# 搜索所有PDF文件中的康芝药业
base_dirs = [
    r"D:\BaiduNetdiskDownload\data\附件2：财务报告\reports-深交所",
    r"D:\BaiduNetdiskDownload\data\附件2：财务报告\reports-上交所",
]

keywords = ["康芝药业", "300086"]
found = []

for base_dir in base_dirs:
    if not os.path.exists(base_dir):
        continue

    pdf_files = [f for f in os.listdir(base_dir) if f.endswith(".pdf")]
    print(f"Searching {len(pdf_files)} files in {base_dir}...")

    for idx, pdf_file in enumerate(pdf_files):
        if idx % 100 == 0:
            print(f"  Progress: {idx}/{len(pdf_files)}")

        pdf_path = os.path.join(base_dir, pdf_file)

        try:
            with pdfplumber.open(pdf_path) as pdf:
                text = ""
                for page in pdf.pages[:2]:  # 只读前2页
                    try:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text
                    except:
                        pass

                if any(kw in text for kw in keywords):
                    print(f"\n*** FOUND: {pdf_file} ***")
                    found.append(pdf_file)
        except:
            pass

print(f"\n\nTotal found: {len(found)}")
if found:
    for f in found:
        print(f"  - {f}")
else:
    print("No PDF files contain '康芝药业' or '300086'")
