from __future__ import annotations

import re
from collections import defaultdict
from typing import Optional

import pymysql

from config import DB_CONFIG


NUM_RE = re.compile(r"(?<!\d)-?\d{1,3}(?:,\d{3})*(?:\.\d+)?(?!\d)")

FIELD_ALIASES = {
    "operating_expense_selling_expenses": ["销售费用"],
    "operating_expense_rnd_expenses": ["研发费用"],
    "operating_expense_administrative_expenses": ["管理费用"],
    "operating_expense_financial_expenses": ["财务费用"],
    "operating_expense_taxes_and_surcharges": ["税金及附加"],
    "operating_expense_cost_of_sales": ["营业成本"],
}


def parse_num(s: str) -> Optional[float]:
    try:
        return float((s or "").replace(",", ""))
    except Exception:
        return None


def extract_value_near_keyword(text: str, keyword: str) -> Optional[float]:
    if not text or keyword not in text:
        return None
    # Prefer first numeric value right after the keyword (usually current-period value).
    for m in re.finditer(keyword, text):
        st = m.end()
        ed = min(len(text), st + 80)
        chunk = text[st:ed]
        nums = [parse_num(x) for x in NUM_RE.findall(chunk)]
        nums = [x for x in nums if x is not None]
        if nums:
            return nums[0]
    return None


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
                SELECT file_path, LPAD(stock_code,6,'0') AS stock_code, report_year, report_period
                FROM sse_report_index
                WHERE stock_code REGEXP '^[0-9]{6}$' AND report_year IS NOT NULL
                UNION ALL
                SELECT file_path, LPAD(stock_code,6,'0') AS stock_code, report_year, report_period
                FROM szse_report_index
                WHERE stock_code REGEXP '^[0-9]{6}$' AND report_year IS NOT NULL
                """
            )
            meta_rows = cur.fetchall()
            meta_by_file = {r["file_path"]: r for r in meta_rows}

            kw_regex = "|".join(
                [re.escape(k) for aliases in FIELD_ALIASES.values() for k in aliases]
            )
            cur.execute(
                f"""
                SELECT file_path, page_text
                FROM sh_reports_raw_pages
                WHERE page_text REGEXP %s
                """,
                (kw_regex,),
            )
            page_rows = cur.fetchall()

            text_by_file = defaultdict(list)
            for r in page_rows:
                text_by_file[r["file_path"]].append(r["page_text"] or "")

            updates = 0
            for fp, texts in text_by_file.items():
                meta = meta_by_file.get(fp)
                if not meta:
                    continue
                merged = "\n".join(texts)
                for field_name, aliases in FIELD_ALIASES.items():
                    v = None
                    for a in aliases:
                        v = extract_value_near_keyword(merged, a)
                        if v is not None:
                            break
                    if v is None:
                        continue
                    cur.execute(
                        f"""
                        UPDATE income_sheet
                        SET {field_name}=%s
                        WHERE LPAD(stock_code,6,'0')=%s
                          AND report_year=%s
                          AND report_period=%s
                          AND {field_name} IS NULL
                        """,
                        (
                            v,
                            meta["stock_code"],
                            meta["report_year"],
                            meta["report_period"],
                        ),
                    )
                    updates += cur.rowcount

        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) c FROM income_sheet WHERE operating_expense_rnd_expenses IS NOT NULL")
            rnd_c = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) c FROM income_sheet WHERE operating_expense_selling_expenses IS NOT NULL")
            sell_c = cur.fetchone()["c"]
        print(f"income_expense_backfill_updates={updates}, rnd_non_null={rnd_c}, sell_non_null={sell_c}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
