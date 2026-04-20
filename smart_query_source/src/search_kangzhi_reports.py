# -*- coding: utf-8 -*-
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    import pdfplumber
except ImportError:
    print("需要安装 pdfplumber: pip install pdfplumber")
    sys.exit(1)


def extract_text_from_pdf(pdf_path, max_pages=5):
    """提取PDF前N页的文本"""
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages[:max_pages]):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                except:
                    pass
    except Exception as e:
        return ""
    return text


def search_in_reports():
    """在研报目录中搜索康芝药业"""
    base_dirs = [
        (r"D:\BaiduNetdiskDownload\data\附件5：研报数据\个股研报", "个股研报"),
        (r"D:\BaiduNetdiskDownload\data\附件5：研报数据\行业研报", "行业研报"),
    ]

    keywords = ["康芝药业", "300086", "Kangzhi", "儿童药"]
    found_files = []

    for base_dir, dir_name in base_dirs:
        if not os.path.exists(base_dir):
            print(f"目录不存在: {base_dir}")
            continue

        print(f"\n扫描目录: {dir_name} ({base_dir})")
        pdf_files = [f for f in os.listdir(base_dir) if f.lower().endswith(".pdf")]
        print(f"  找到 {len(pdf_files)} 个PDF文件")

        for idx, pdf_file in enumerate(pdf_files):
            pdf_path = os.path.join(base_dir, pdf_file)

            # 显示进度
            if (idx + 1) % 20 == 0 or idx == 0:
                print(f"  正在扫描: {idx + 1}/{len(pdf_files)} - {pdf_file[:50]}")

            try:
                text = extract_text_from_pdf(pdf_path, max_pages=3)
                if text and any(kw in text for kw in keywords):
                    print(f"\n  *** 找到匹配: {pdf_file} ***")
                    # 显示匹配内容
                    for kw in keywords:
                        if kw in text:
                            idx_pos = text.find(kw)
                            context = text[
                                max(0, idx_pos - 50) : min(len(text), idx_pos + 100)
                            ]
                            print(f"    上下文: ...{context}...")
                    found_files.append((pdf_path, pdf_file, dir_name))
            except Exception as e:
                continue

    return found_files


if __name__ == "__main__":
    print("=" * 70)
    print("在研报数据中搜索康芝药业(300086)")
    print("=" * 70)

    found = search_in_reports()

    print("\n" + "=" * 70)
    print(f"搜索完成! 找到 {len(found)} 个包含康芝药业的文件")
    print("=" * 70)

    if found:
        for path, name, dir_type in found:
            print(f"\n[{dir_type}] {name}")
            print(f"  路径: {path}")
