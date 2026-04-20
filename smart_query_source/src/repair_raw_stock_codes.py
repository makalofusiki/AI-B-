from __future__ import annotations

import re

import pymysql

from config import DB_CONFIG


def extract_name(file_name: str) -> str:
    s = file_name or ""
    s = s.rsplit(".", 1)[0]
    for sep in ["：", ":", "_"]:
        if sep in s:
            s = s.split(sep, 1)[0]
            break
    return s.strip()


def normalize_name(name: str) -> str:
    s = (name or "").replace("\u3000", " ")
    s = re.sub(r"\s+", "", s)
    s = s.replace("：", "").replace(":", "")
    return s.strip()


def main():
    conn = pymysql.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
        charset=DB_CONFIG["charset"],
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT stock_code, stock_abbr, company_name FROM listed_company_basic_info")
            rows = cur.fetchall()
            abbr_to_code = {}
            company_to_code = {}
            for r in rows:
                code = str(r["stock_code"]).zfill(6) if str(r["stock_code"]).isdigit() else str(r["stock_code"])
                abbr = normalize_name(str(r["stock_abbr"]))
                cname = normalize_name(str(r["company_name"]))
                if abbr:
                    abbr_to_code[abbr] = code
                if cname:
                    company_to_code[cname] = code

            cur.execute(
                """
                SELECT DISTINCT file_name
                FROM sh_reports_raw_pages
                WHERE stock_code IS NULL OR stock_code NOT REGEXP '^[0-9]{3,6}$'
                """
            )
            files = [r["file_name"] for r in cur.fetchall()]

            fixed = 0
            for fn in files:
                name = normalize_name(extract_name(fn))
                code = abbr_to_code.get(name)
                if not code:
                    code = company_to_code.get(name)
                if not code:
                    # fallback: longest abbr contained in name
                    best = None
                    for abbr, c in abbr_to_code.items():
                        if abbr and abbr in name:
                            if best is None or len(abbr) > len(best[0]):
                                best = (abbr, c)
                    if best is None:
                        for cname, c in company_to_code.items():
                            if cname and cname in name:
                                if best is None or len(cname) > len(best[0]):
                                    best = (cname, c)
                    if best:
                        code = best[1]
                if code:
                    cur.execute(
                        "UPDATE sh_reports_raw_pages SET stock_code=%s WHERE file_name=%s",
                        (code, fn),
                    )
                    fixed += cur.rowcount

            conn.commit()
            print(f"raw pages fixed={fixed}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
