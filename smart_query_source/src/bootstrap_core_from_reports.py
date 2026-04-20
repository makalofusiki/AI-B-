from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from typing import Dict, Any, Optional

import pymysql

from config import DB_CONFIG


METRIC_PATTERNS = {
    "total_profit": [r"利润总额"],
    "net_profit": [r"净利润"],
    "total_operating_revenue": [r"营业总收入"],
    "asset_total_assets": [r"总资产"],
    "liability_total_liabilities": [r"总负债"],
    "asset_liability_ratio": [r"资产负债率"],
    "eps": [r"基本每股收益", r"每股收益"],
    "net_cash_flow": [r"净现金流", r"现金及现金等价物净增加额"],
}

NUMBER_RE = re.compile(r"(?<!\d)-?\d{1,3}(?:,\d{3})*(?:\.\d+)?(?!\d)")


def clean_number(s: str) -> Optional[float]:
    if not s:
        return None
    s = s.replace(",", "")
    try:
        return float(s)
    except Exception:
        return None


def period_from_report_date(d: Optional[date]) -> str:
    if d is None:
        return "FY"
    md = (d.month, d.day)
    if md <= (3, 31):
        return "Q1"
    if md <= (6, 30):
        return "HY"
    if md <= (9, 30):
        return "Q3"
    return "FY"


def pick_metric_value(metric: str, text: str, aliases) -> Optional[float]:
    best = None
    for alias in aliases:
        for m in re.finditer(alias, text):
            start = max(0, m.start() - 80)
            end = min(len(text), m.end() + 220)
            chunk = text[start:end]
            nums = [clean_number(x) for x in NUMBER_RE.findall(chunk)]
            nums = [x for x in nums if x is not None]
            if nums:
                if metric == "eps":
                    candidates = [n for n in nums if -20 <= n <= 20]
                    candidate = candidates[0] if candidates else None
                elif metric == "asset_liability_ratio":
                    candidates = [n for n in nums if 0 <= n <= 1000]
                    candidate = candidates[0] if candidates else None
                else:
                    # Amount metrics: prefer larger absolute numbers in vicinity.
                    candidates = [n for n in nums if abs(n) >= 100]
                    if not candidates:
                        candidates = nums
                    candidate = max(candidates, key=lambda x: abs(x))
                if candidate is None:
                    continue
                if best is None:
                    best = candidate
    return best


def sanitize_metric(metric: str, v: Optional[float]) -> Optional[float]:
    if v is None:
        return None
    av = abs(v)
    if metric == "eps":
        if av > 100:
            return None
    if metric == "asset_liability_ratio":
        if av > 1000:
            return None
    if metric in {"total_profit", "net_profit", "total_operating_revenue", "asset_total_assets", "liability_total_liabilities", "net_cash_flow"}:
        if av > 1e14:
            return None
    return v


def derive_report_year(report_date: date, period: str) -> int:
    y = report_date.year
    if period == "FY" and report_date.month <= 4:
        return y - 1
    return y


def infer_period_year(file_name: str, report_date: date, header_text: str):
    t = header_text or ""
    m = re.search(r"(20\d{2})年(第一季度报告|一季度报告|半年度报告|第三季度报告|三季度报告|年度报告)", t)
    if m:
        y = int(m.group(1))
        marker = m.group(2)
        if "一季度" in marker:
            return "Q1", y
        if "半年度" in marker:
            return "HY", y
        if "三季度" in marker:
            return "Q3", y
        return "FY", y

    period = period_from_report_date(report_date)
    year = derive_report_year(report_date, period)
    if period == "HY" and report_date.month <= 4:
        # Annual reports published in Apr are often misclassified by date heuristic.
        period = "FY"
        year = report_date.year - 1
    return period, year


def infer_period_year_from_filename(file_name: str):
    t = (file_name or "").replace("（", "(").replace("）", ")")
    m = re.search(r"(20\d{2})年(第一季度|一季度|半年度|第三季度|三季度|年度|年年度)", t)
    if not m:
        m = re.search(r"(20\d{2})(?:年)?(Q1|Q3|HY|FY)", t, re.I)
        if m:
            y = int(m.group(1))
            p = m.group(2).upper()
            return p, y
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
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT stock_code, stock_abbr
                FROM listed_company_basic_info
                """
            )
            abbr_rows = cur.fetchall()

        abbr_map = {}
        for r in abbr_rows:
            code = str(r["stock_code"])
            abbr = r["stock_abbr"]
            abbr_map[code] = abbr
            if code.isdigit():
                abbr_map[code.zfill(6)] = abbr

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT file_path, file_name, stock_code, report_date, page_no, page_text
                FROM sh_reports_raw_pages
                WHERE page_text REGEXP '利润总额|净利润|营业总收入|总资产|总负债|资产负债率|每股收益|净现金流|现金及现金等价物净增加额'
                  AND stock_code IS NOT NULL
                ORDER BY file_path, page_no
                """
            )
            rows = cur.fetchall()

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT file_path, page_no, page_text
                FROM sh_reports_raw_pages
                WHERE page_no <= 5
                ORDER BY file_path, page_no
                """
            )
            head_rows = cur.fetchall()

        header_map = defaultdict(list)
        for r in head_rows:
            header_map[r["file_path"]].append(r["page_text"] or "")

        files = defaultdict(lambda: {"texts": [], "stock_code": None, "report_date": None, "file_name": None})
        for r in rows:
            key = r["file_path"]
            files[key]["texts"].append(r["page_text"] or "")
            files[key]["stock_code"] = str(r["stock_code"])
            files[key]["report_date"] = r["report_date"]
            files[key]["file_name"] = r["file_name"]

        # key -> best record with more filled metrics
        best_records: Dict[tuple, Dict[str, Any]] = {}
        for _, f in files.items():
            code = f["stock_code"]
            rdate = f["report_date"]
            period = None
            year = None
            if rdate:
                header_text = "\n".join(header_map.get(_, []))
                period, year = infer_period_year(f["file_name"] or "", rdate, header_text)
            else:
                period, year = infer_period_year_from_filename(f["file_name"] or "")
            if year is None:
                continue
            key = (code, year, period)

            text = "\n".join(f["texts"])
            rec = {
                "stock_code": code,
                "stock_abbr": abbr_map.get(code) or abbr_map.get(code.zfill(6)) if code.isdigit() else None,
                "report_year": year,
                "report_period": period,
                "metrics": {},
            }
            for m, aliases in METRIC_PATTERNS.items():
                rec["metrics"][m] = sanitize_metric(m, pick_metric_value(m, text, aliases))

            if rec["metrics"].get("asset_liability_ratio") is None:
                a = rec["metrics"].get("asset_total_assets")
                l = rec["metrics"].get("liability_total_liabilities")
                if a and a != 0 and l is not None:
                    rec["metrics"]["asset_liability_ratio"] = l / a * 100

            filled = sum(1 for v in rec["metrics"].values() if v is not None)
            prev = best_records.get(key)
            if prev is None:
                best_records[key] = rec
            else:
                prev_filled = sum(1 for v in prev["metrics"].values() if v is not None)
                if filled > prev_filled:
                    best_records[key] = rec

        recs = list(best_records.values())
        recs.sort(key=lambda x: (x["stock_code"], x["report_year"], x["report_period"]))

        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE income_sheet")
            cur.execute("TRUNCATE TABLE balance_sheet")
            cur.execute("TRUNCATE TABLE cash_flow_sheet")
            cur.execute("TRUNCATE TABLE core_performance_indicators_sheet")

            serial = 1
            for r in recs:
                code = r["stock_code"]
                abbr = r["stock_abbr"]
                yr = r["report_year"]
                pd = r["report_period"]
                m = r["metrics"]

                cur.execute(
                    """
                    INSERT INTO income_sheet
                    (serial_number, stock_code, stock_abbr, total_profit, net_profit, total_operating_revenue, report_period, report_year)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (serial, code, abbr, m.get("total_profit"), m.get("net_profit"), m.get("total_operating_revenue"), pd, yr),
                )
                cur.execute(
                    """
                    INSERT INTO balance_sheet
                    (serial_number, stock_code, stock_abbr, asset_total_assets, liability_total_liabilities, asset_liability_ratio, report_period, report_year)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (serial, code, abbr, m.get("asset_total_assets"), m.get("liability_total_liabilities"), m.get("asset_liability_ratio"), pd, yr),
                )
                cur.execute(
                    """
                    INSERT INTO cash_flow_sheet
                    (serial_number, stock_code, stock_abbr, net_cash_flow, report_period, report_year)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    """,
                    (serial, code, abbr, m.get("net_cash_flow"), pd, yr),
                )
                cur.execute(
                    """
                    INSERT INTO core_performance_indicators_sheet
                    (serial_number, stock_code, stock_abbr, eps, report_period, report_year)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    """,
                    (serial, code, abbr, m.get("eps"), pd, yr),
                )
                serial += 1

        conn.commit()

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) c FROM income_sheet")
            c_income = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) c FROM balance_sheet")
            c_balance = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) c FROM cash_flow_sheet")
            c_cash = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) c FROM core_performance_indicators_sheet")
            c_core = cur.fetchone()["c"]
        print(f"loaded income_sheet={c_income}, balance_sheet={c_balance}, cash_flow_sheet={c_cash}, core_performance_indicators_sheet={c_core}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
