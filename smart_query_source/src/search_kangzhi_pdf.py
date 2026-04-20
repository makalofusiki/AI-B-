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
    print("请运行: pip install pdfplumber")
    sys.exit(1)

print(f"使用PDF库: {PDF_LIB}")


def extract_text_from_pdf(pdf_path):
    """提取PDF前3页的文本"""
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages[:3]):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                except:
                    pass
    except Exception as e:
        return f"ERROR: {e}"
    return text


def search_kangzhi_in_pdfs():
    """搜索包含康芝药业的PDF文件"""
    base_dirs = [
        r"D:\BaiduNetdiskDownload\data\附件2：财务报告\reports-上交所",
        r"D:\BaiduNetdiskDownload\data\附件2：财务报告\reports-深交所",
        r"D:\BaiduNetdiskDownload\data\附件5：研报数据\个股研报",
        r"D:\BaiduNetdiskDownload\data\附件5：研报数据\行业研报",
    ]

    keywords = ["康芝药业", "300086"]
    found_files = []

    for base_dir in base_dirs:
        if not os.path.exists(base_dir):
            print(f"目录不存在: {base_dir}")
            continue

        print(f"\n扫描目录: {base_dir}")
        pdf_files = [f for f in os.listdir(base_dir) if f.endswith(".pdf")]
        print(f"  找到 {len(pdf_files)} 个PDF文件")

        # 只扫描前20个文件作为示例
        for pdf_file in pdf_files[:20]:
            pdf_path = os.path.join(base_dir, pdf_file)

            # 先检查文件名
            if any(kw in pdf_file for kw in keywords):
                print(f"  [文件名匹配] {pdf_file}")
                found_files.append(pdf_path)
                continue

            # 检查文件内容前3页
            try:
                text = extract_text_from_pdf(pdf_path)
                if any(kw in text for kw in keywords):
                    print(f"  [内容匹配] {pdf_file}")
                    found_files.append(pdf_path)
            except Exception as e:
                print(f"  [错误] {pdf_file}: {e}")

    return found_files


if __name__ == "__main__":
    print("=" * 60)
    print("搜索康芝药业(300086) PDF文件")
    print("=" * 60)

    found = search_kangzhi_in_pdfs()

    print("\n" + "=" * 60)
    print(f"搜索结果: 找到 {len(found)} 个文件")
    print("=" * 60)
    for f in found:
        print(f"  {f}")
