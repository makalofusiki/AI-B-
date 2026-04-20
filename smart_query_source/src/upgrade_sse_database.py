from __future__ import annotations

import argparse
import re
from collections import defaultdict
from datetime import date
from typing import Optional

import pymysql

from config import DB_CONFIG


NUM_RE = re.compile(r"(?<!\d)-?\d{1,3}(?:,\d{3})*(?:\.\d+)?(?!\d)")

METRICS = {
    "total_profit": ["利润总额"],
    "net_profit": ["净利润"],
    "total_operating_revenue": ["营业总收入", "主营业务收入"],
    "asset_total_assets": ["总资产"],
    "liability_total_liabilities": ["总负债"],
    "asset_liability_ratio": ["资产负债率"],
    "eps": ["基本每股收益", "每股收益"],
    "net_cash_flow": ["净现金流", "现金及现金等价物净增加额"],
}


def normalize_name(name: str) -> str:
    s = (name or "").replace("\u3000", " ")
    s = re.sub(r"\s+", "", s)
    s = s.replace("：", "").replace(":", "")
    return s.strip()


def extract_name(file_name: str) -> str:
    s = (file_name or "").rsplit(".", 1)[0]
    for sep in ["：", ":", "_"]:
        if sep in s:
            s = s.split(sep, 1)[0]
            break
    return s.strip()


def parse_num(s: str) -> Optional[float]:
    if not s:
        return None
    try:
        return float(s.replace(",", ""))
    except Exception:
        return None


def infer_period(report_date: Optional[date], file_name: str):
    if report_date:
        if report_date.month <= 3:
            return "Q1", report_date.year
        if report_date.month <= 6:
            return "HY", report_date.year
        if report_date.month <= 9:
            return "Q3", report_date.year
        y = report_date.year - 1 if report_date.month <= 4 else report_date.year
        return "FY", y
    t = file_name or ""
    m = re.search(r"(20\d{2})年(第一季度|一季度|半年度|第三季度|三季度|年度|年年度)", t)
    if m:
        y = int(m.group(1))
        mk = m.group(2)
        if "一季度" in mk:
            return "Q1", y
        if "半年度" in mk:
            return "HY", y
        if "三季度" in mk:
            return "Q3", y
        return "FY", y
    if report_date:
        return "FY", report_date.year
    return "FY", None


def extract_metric(text: str, aliases):
    best = None
    snippet = None
    for a in aliases:
        for m in re.finditer(a, text):
            st = max(0, m.start() - 80)
            ed = min(len(text), m.end() + 220)
            chunk = text[st:ed]
            nums = [parse_num(x) for x in NUM_RE.findall(chunk)]
            nums = [x for x in nums if x is not None]
            if not nums:
                continue
            cand = max(nums, key=lambda x: abs(x))
            if best is None:
                best = cand
                snippet = chunk[:300]
    return best, snippet


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exchange", choices=["sse", "szse"], default="sse")
    args = parser.parse_args()
    if args.exchange == "sse":
        report_like = "%reports-上交所%"
        index_table = "sse_report_index"
        facts_table = "sse_financial_facts"
    else:
        report_like = "%reports-深交所%"
        index_table = "szse_report_index"
        facts_table = "szse_financial_facts"

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
                f"""
                CREATE TABLE IF NOT EXISTS {index_table} (
                  id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  file_path VARCHAR(700) NOT NULL,
                  file_name VARCHAR(255) NOT NULL,
                  stock_code VARCHAR(20),
                  stock_abbr VARCHAR(100),
                  company_name VARCHAR(255),
                  report_year INT,
                  report_period VARCHAR(20),
                  page_count INT,
                  UNIQUE KEY uk_file_path (file_path(255)),
                  KEY idx_stock_period (stock_code, report_year, report_period)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """
            )
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {facts_table} (
                  id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  file_path VARCHAR(700) NOT NULL,
                  stock_code VARCHAR(20),
                  report_year INT,
                  report_period VARCHAR(20),
                  metric_key VARCHAR(100) NOT NULL,
                  metric_value DECIMAL(30,6),
                  snippet TEXT,
                  UNIQUE KEY uk_fact (file_path(255), metric_key),
                  KEY idx_metric (stock_code, report_year, report_period, metric_key)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """
            )

            cur.execute("SELECT LPAD(stock_code,6,'0') stock_code, stock_abbr, company_name FROM listed_company_basic_info")
            company_rows = cur.fetchall()
            companies = {r["stock_code"]: r for r in company_rows}
            abbr_to_code = {}
            company_to_code = {}
            for r in company_rows:
                abbr = normalize_name(r["stock_abbr"] or "")
                cname = normalize_name(r["company_name"] or "")
                if abbr:
                    abbr_to_code[abbr] = r["stock_code"]
                if cname:
                    company_to_code[cname] = r["stock_code"]

            cur.execute(
                """
                SELECT file_path,
                       MIN(file_name) AS file_name,
                       MIN(LPAD(stock_code,6,'0')) AS stock_code,
                       MIN(report_date) AS report_date,
                       COUNT(*) AS page_count
                FROM sh_reports_raw_pages
                WHERE file_path LIKE %s
                GROUP BY file_path
                """,
                (report_like,),
            )
            docs = cur.fetchall()

            for d in docs:
                code = (d["stock_code"] or "").strip()
                if not re.fullmatch(r"\d{6}", code):
                    m = re.match(r"(\d{6})_", d["file_name"] or "")
                    code = m.group(1) if m else code
                if not re.fullmatch(r"\d{6}", code):
                    doc_name = normalize_name(extract_name(d["file_name"] or ""))
                    code = abbr_to_code.get(doc_name) or company_to_code.get(doc_name) or code
                period, year = infer_period(d["report_date"], d["file_name"])
                c = companies.get(code, {})
                cur.execute(
                    f"""
                    INSERT INTO {index_table}(file_path,file_name,stock_code,stock_abbr,company_name,report_year,report_period,page_count)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                      file_name=VALUES(file_name),
                      stock_code=VALUES(stock_code),
                      stock_abbr=VALUES(stock_abbr),
                      company_name=VALUES(company_name),
                      report_year=VALUES(report_year),
                      report_period=VALUES(report_period),
                      page_count=VALUES(page_count)
                    """,
                    (d["file_path"], d["file_name"], code, c.get("stock_abbr"), c.get("company_name"), year, period, d["page_count"]),
                )

            cur.execute(
                """
                SELECT file_path, page_text
                FROM sh_reports_raw_pages
                WHERE file_path LIKE %s
                  AND page_text REGEXP '利润总额|净利润|营业总收入|主营业务收入|总资产|总负债|资产负债率|每股收益|净现金流|现金及现金等价物净增加额'
                """,
                (report_like,),
            )
            page_rows = cur.fetchall()

            text_by_file = defaultdict(list)
            for r in page_rows:
                text_by_file[r["file_path"]].append(r["page_text"] or "")

            cur.execute(f"SELECT file_path, stock_code, report_year, report_period FROM {index_table}")
            doc_meta = {r["file_path"]: r for r in cur.fetchall()}

            for fp, texts in text_by_file.items():
                meta = doc_meta.get(fp)
                if not meta:
                    continue
                merged = "\n".join(texts)
                for metric_key, aliases in METRICS.items():
                    v, snip = extract_metric(merged, aliases)
                    cur.execute(
                        f"""
                        INSERT INTO {facts_table}(file_path,stock_code,report_year,report_period,metric_key,metric_value,snippet)
                        VALUES(%s,%s,%s,%s,%s,%s,%s)
                        ON DUPLICATE KEY UPDATE
                          stock_code=VALUES(stock_code),
                          report_year=VALUES(report_year),
                          report_period=VALUES(report_period),
                          metric_value=VALUES(metric_value),
                          snippet=VALUES(snippet)
                        """,
                        (fp, meta["stock_code"], meta["report_year"], meta["report_period"], metric_key, v, snip),
                    )

            # Merge extracted facts into core tables
            cur.execute(f"SELECT DISTINCT stock_code, report_year, report_period FROM {index_table} WHERE stock_code REGEXP '^[0-9]{6}$' AND report_year IS NOT NULL")
            keys = cur.fetchall()
            cur.execute("SELECT LPAD(stock_code,6,'0') stock_code, report_year, report_period FROM income_sheet")
            existing = {(r["stock_code"], r["report_year"], r["report_period"]) for r in cur.fetchall()}
            cur.execute("SELECT COALESCE(MAX(serial_number),0) m FROM income_sheet")
            serial = int(cur.fetchone()["m"] or 0) + 1

            for k in keys:
                key = (k["stock_code"], k["report_year"], k["report_period"])
                if key not in existing:
                    c = companies.get(k["stock_code"], {})
                    cur.execute(
                        "INSERT INTO income_sheet(serial_number,stock_code,stock_abbr,report_year,report_period) VALUES(%s,%s,%s,%s,%s)",
                        (serial, k["stock_code"], c.get("stock_abbr"), k["report_year"], k["report_period"]),
                    )
                    cur.execute(
                        "INSERT INTO balance_sheet(serial_number,stock_code,stock_abbr,report_year,report_period) VALUES(%s,%s,%s,%s,%s)",
                        (serial, k["stock_code"], c.get("stock_abbr"), k["report_year"], k["report_period"]),
                    )
                    cur.execute(
                        "INSERT INTO cash_flow_sheet(serial_number,stock_code,stock_abbr,report_year,report_period) VALUES(%s,%s,%s,%s,%s)",
                        (serial, k["stock_code"], c.get("stock_abbr"), k["report_year"], k["report_period"]),
                    )
                    cur.execute(
                        "INSERT INTO core_performance_indicators_sheet(serial_number,stock_code,stock_abbr,report_year,report_period) VALUES(%s,%s,%s,%s,%s)",
                        (serial, k["stock_code"], c.get("stock_abbr"), k["report_year"], k["report_period"]),
                    )
                    existing.add(key)
                    serial += 1

            # update fields only when null
            updates = [
                ("income_sheet", "total_profit", "total_profit", 1e14),
                ("income_sheet", "net_profit", "net_profit", 1e14),
                ("income_sheet", "total_operating_revenue", "total_operating_revenue", 1e14),
                ("balance_sheet", "asset_total_assets", "asset_total_assets", 1e14),
                ("balance_sheet", "liability_total_liabilities", "liability_total_liabilities", 1e14),
                ("balance_sheet", "asset_liability_ratio", "asset_liability_ratio", 1000),
                ("cash_flow_sheet", "net_cash_flow", "net_cash_flow", 1e14),
                ("core_performance_indicators_sheet", "eps", "eps", 1000),
            ]
            for table, field, metric_key, max_abs in updates:
                cur.execute(
                    f"""
                    UPDATE {table} t
                    JOIN (
                      SELECT stock_code, report_year, report_period, MAX(metric_value) AS metric_value
                      FROM {facts_table}
                      WHERE metric_key=%s AND metric_value IS NOT NULL AND ABS(metric_value) <= %s
                      GROUP BY stock_code, report_year, report_period
                    ) f
                      ON LPAD(t.stock_code,6,'0')=LPAD(f.stock_code,6,'0')
                     AND t.report_year=f.report_year
                     AND t.report_period=f.report_period
                    SET t.{field}=f.metric_value
                    WHERE t.{field} IS NULL
                    """,
                    (metric_key, max_abs),
                )

        conn.commit()

        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) c FROM {index_table}")
            idx = cur.fetchone()["c"]
            cur.execute(f"SELECT COUNT(*) c FROM {facts_table}")
            facts = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) c FROM income_sheet")
            income = cur.fetchone()["c"]
        print(f"{index_table}={idx}, {facts_table}={facts}, income_sheet={income}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
