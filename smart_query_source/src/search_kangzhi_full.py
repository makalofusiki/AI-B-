# -*- coding: utf-8 -*-
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    import pdfplumber

    PDF_LIB = "pdfplumber"
except ImportError:
    print("错误：需要安装 pdfplumber")
    sys.exit(1)

print(f"使用PDF库: {PDF_LIB}")


def extract_text_from_pdf(pdf_path, max_pages=2):
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


def search_all_pdfs():
    """搜索所有PDF文件中的康芝药业"""
    base_dirs = [
        (r"D:\BaiduNetdiskDownload\data\附件2：财务报告\reports-上交所", "上交所"),
        (r"D:\BaiduNetdiskDownload\data\附件2：财务报告\reports-深交所", "深交所"),
        (r"D:\BaiduNetdiskDownload\data\附件5：研报数据\个股研报", "个股研报"),
        (r"D:\BaiduNetdiskDownload\data\附件5：研报数据\行业研报", "行业研报"),
    ]

    keywords = ["康芝药业", "300086", "Kangzhi", "KANGZHI"]
    found_files = []
    total_scanned = 0

    for base_dir, dir_name in base_dirs:
        if not os.path.exists(base_dir):
            print(f"目录不存在: {base_dir}")
            continue

        print(f"\n扫描目录: {dir_name}")
        pdf_files = [f for f in os.listdir(base_dir) if f.lower().endswith(".pdf")]
        print(f"  找到 {len(pdf_files)} 个PDF文件")

        for idx, pdf_file in enumerate(pdf_files):
            pdf_path = os.path.join(base_dir, pdf_file)
            total_scanned += 1

            # 显示进度
            if (idx + 1) % 50 == 0:
                print(f"  已扫描 {idx + 1}/{len(pdf_files)} 个文件...")

            # 先检查文件名（包括编码后的文件名）
            if any(kw in pdf_file for kw in keywords):
                print(f"  [文件名匹配] {pdf_file}")
                found_files.append((pdf_path, pdf_file, "文件名匹配"))
                continue

            # 检查文件内容
            try:
                text = extract_text_from_pdf(pdf_path, max_pages=2)
                if text and any(kw in text for kw in keywords):
                    print(f"  [内容匹配] {pdf_file}")
                    # 显示匹配内容
                    for kw in keywords:
                        if kw in text:
                            idx_pos = text.find(kw)
                            context = text[
                                max(0, idx_pos - 30) : min(len(text), idx_pos + 30)
                            ]
                            print(f"    -> ...{context}...")
                    found_files.append((pdf_path, pdf_file, "内容匹配"))
            except Exception as e:
                continue

    return found_files, total_scanned


if __name__ == "__main__":
    print("=" * 60)
    print("完整搜索康芝药业(300086) PDF文件")
    print("=" * 60)

    found, total = search_all_pdfs()

    print("\n" + "=" * 60)
    print(f"搜索完成!")
    print(f"总扫描文件数: {total}")
    print(f"匹配文件数: {len(found)}")
    print("=" * 60)

    if found:
        print("\n找到的文件:")
        for path, name, match_type in found:
            print(f"  [{match_type}] {name}")
            print(f"    路径: {path}")
    else:
        print("\n未找到包含'康芝药业'或'300086'的PDF文件")
        print("\n结论: 康芝药业的财务报告PDF确实不存在于附件目录中")
