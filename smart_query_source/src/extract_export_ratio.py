from __future__ import annotations

import re
from collections import defaultdict

import pymysql

from config import DB_CONFIG


PERCENT_RE = re.compile(r"([0-9]{1,3}(?:\.[0-9]+)?)\s*%")
KEY_RE = re.compile(r"出口.{0,24}(?:占比|占营业收入比重|收入占比|占主营业务收入比重)")


def extract_ratio(text: str):
    if not text:
        return None, None
    for m in KEY_RE.finditer(text):
        st = max(0, m.start() - 40)
        ed = min(len(text), m.end() + 80)
        chunk = text[st:ed]
        p = PERCENT_RE.search(chunk)
        if p:
            try:
                v = float(p.group(1))
                return v, chunk[:300]
            except Exception:
                continue
    return None, None


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
            cur.execute(
                """
                SELECT file_path, LPAD(stock_code,6,'0') AS stock_code, report_year, report_period, stock_abbr
                FROM sse_report_index
                WHERE stock_code REGEXP '^[0-9]{6}$' AND report_year IS NOT NULL
                UNION ALL
                SELECT file_path, LPAD(stock_code,6,'0') AS stock_code, report_year, report_period, stock_abbr
                FROM szse_report_index
                WHERE stock_code REGEXP '^[0-9]{6}$' AND report_year IS NOT NULL
                """
            )
            meta_rows = cur.fetchall()
            meta_by_file = {r["file_path"]: r for r in meta_rows}

            cur.execute(
                """
                SELECT file_path, page_text
                FROM sh_reports_raw_pages
                WHERE page_text REGEXP '出口.{0,24}(占比|占营业收入比重|收入占比|占主营业务收入比重)'
                """
            )
            page_rows = cur.fetchall()

            texts = defaultdict(list)
            for r in page_rows:
                texts[r["file_path"]].append(r["page_text"] or "")

            upserts = 0
            for fp, pages in texts.items():
                meta = meta_by_file.get(fp)
                if not meta:
                    continue
                val = None
                snip = None
                for t in pages:
                    v, s = extract_ratio(t)
                    if v is not None:
                        val = v
                        snip = s
                        break
                if val is None:
                    continue
                cur.execute(
                    """
                    INSERT INTO report_export_ratio(stock_code, stock_abbr, report_year, report_period, export_ratio_pct, source_file, snippet)
                    VALUES(%s,%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                      stock_abbr=VALUES(stock_abbr),
                      export_ratio_pct=VALUES(export_ratio_pct),
                      source_file=VALUES(source_file),
                      snippet=VALUES(snippet)
                    """,
                    (
                        meta["stock_code"],
                        meta.get("stock_abbr"),
                        meta["report_year"],
                        meta["report_period"],
                        val,
                        fp,
                        snip,
                    ),
                )
                upserts += 1
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM report_export_ratio")
            total = cur.fetchone()["c"]
        print(f"export_ratio_upserts={upserts}, total_rows={total}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
