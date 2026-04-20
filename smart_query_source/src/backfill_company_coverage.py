from __future__ import annotations

from datetime import date

import pymysql

from config import DB_CONFIG


def infer_period(report_date: date) -> str:
    if report_date.month <= 3:
        return "Q1"
    if report_date.month <= 6:
        return "HY"
    if report_date.month <= 9:
        return "Q3"
    return "FY"


def infer_year(report_date: date, period: str) -> int:
    if period == "FY" and report_date.month <= 4:
        return report_date.year - 1
    return report_date.year


def infer_from_filename(file_name: str):
    s = (file_name or "").replace("（", "(").replace("）", ")")
    m = __import__("re").search(r"(20\d{2})年(第一季度|一季度|半年度|第三季度|三季度|年度|年年度)", s)
    if not m:
        return None, None
    y = int(m.group(1))
    marker = m.group(2)
    if "一季度" in marker:
        return "Q1", y
    if "半年度" in marker:
        return "HY", y
    if "三季度" in marker:
        return "Q3", y
    return "FY", y


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
            cur.execute("SELECT LPAD(stock_code,6,'0') stock_code, stock_abbr FROM listed_company_basic_info")
            abbr = {r["stock_code"]: r["stock_abbr"] for r in cur.fetchall()}

            cur.execute(
                """
                SELECT DISTINCT LPAD(stock_code,6,'0') AS stock_code, report_date, file_name
                FROM sh_reports_raw_pages
                WHERE stock_code REGEXP '^[0-9]+$' AND report_date IS NOT NULL
                """
            )
            report_keys = []
            for r in cur.fetchall():
                code = r["stock_code"]
                rd = r["report_date"]
                period = infer_period(rd)
                year = infer_year(rd, period)
                report_keys.append((code, year, period))

            cur.execute(
                """
                SELECT DISTINCT LPAD(stock_code,6,'0') AS stock_code, file_name
                FROM sh_reports_raw_pages
                WHERE stock_code REGEXP '^[0-9]+$' AND report_date IS NULL
                """
            )
            for r in cur.fetchall():
                code = r["stock_code"]
                period, year = infer_from_filename(r["file_name"])
                if year is not None and period is not None:
                    report_keys.append((code, year, period))

            cur.execute("SELECT LPAD(stock_code,6,'0') stock_code, report_year, report_period FROM income_sheet")
            existing = {(r["stock_code"], r["report_year"], r["report_period"]) for r in cur.fetchall()}

            cur.execute("SELECT COALESCE(MAX(serial_number),0) m FROM income_sheet")
            serial = int(cur.fetchone()["m"] or 0) + 1

            added = 0
            for code, year, period in report_keys:
                k = (code, year, period)
                if k in existing:
                    continue
                stock_abbr = abbr.get(code)
                # insert empty rows to ensure company/year/period coverage exists
                cur.execute(
                    "INSERT INTO income_sheet(serial_number,stock_code,stock_abbr,report_year,report_period) VALUES(%s,%s,%s,%s,%s)",
                    (serial, code, stock_abbr, year, period),
                )
                cur.execute(
                    "INSERT INTO balance_sheet(serial_number,stock_code,stock_abbr,report_year,report_period) VALUES(%s,%s,%s,%s,%s)",
                    (serial, code, stock_abbr, year, period),
                )
                cur.execute(
                    "INSERT INTO cash_flow_sheet(serial_number,stock_code,stock_abbr,report_year,report_period) VALUES(%s,%s,%s,%s,%s)",
                    (serial, code, stock_abbr, year, period),
                )
                cur.execute(
                    "INSERT INTO core_performance_indicators_sheet(serial_number,stock_code,stock_abbr,report_year,report_period) VALUES(%s,%s,%s,%s,%s)",
                    (serial, code, stock_abbr, year, period),
                )
                existing.add(k)
                added += 1
                serial += 1

            conn.commit()
            print(f"coverage rows added={added}")

            cur.execute("SELECT COUNT(*) c FROM income_sheet")
            print(f"income_sheet rows={cur.fetchone()['c']}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
