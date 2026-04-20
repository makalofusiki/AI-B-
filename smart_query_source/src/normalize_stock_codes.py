from __future__ import annotations

import pymysql

from config import DB_CONFIG


TABLES = [
    "listed_company_basic_info",
    "income_sheet",
    "balance_sheet",
    "cash_flow_sheet",
    "core_performance_indicators_sheet",
    "stock_research_info",
    "stock_research_raw_pages",
]


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
            for t in TABLES:
                try:
                    cur.execute(
                        f"""
                        UPDATE `{t}`
                        SET stock_code = LPAD(stock_code, 6, '0')
                        WHERE stock_code REGEXP '^[0-9]+$' AND CHAR_LENGTH(stock_code) < 6
                        """
                    )
                    print(f"{t}: normalized")
                except Exception:
                    print(f"{t}: skipped")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
