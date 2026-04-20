from __future__ import annotations

import pymysql

from config import DB_CONFIG


def short_forms(abbr: str):
    suffixes = ["股份", "药业", "制药", "医药", "生物", "集团", "科技", "健康", "中药", "藏药"]
    forms = {abbr}
    for s in suffixes:
        if abbr.endswith(s):
            v = abbr[: -len(s)]
            if len(v) >= 2:
                forms.add(v)
    return forms


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
                CREATE TABLE IF NOT EXISTS company_alias (
                  id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  stock_code VARCHAR(20) NOT NULL,
                  alias VARCHAR(100) NOT NULL,
                  source VARCHAR(30) NOT NULL DEFAULT 'auto',
                  UNIQUE KEY uk_stock_alias (stock_code, alias),
                  KEY idx_alias (alias)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """
            )
            cur.execute("DELETE FROM company_alias WHERE source='auto'")
            cur.execute("SELECT stock_code, stock_abbr FROM listed_company_basic_info")
            rows = cur.fetchall()

            inserts = []
            for r in rows:
                code = str(r["stock_code"]).zfill(6) if str(r["stock_code"]).isdigit() else str(r["stock_code"])
                abbr = (r["stock_abbr"] or "").strip()
                if not abbr:
                    continue
                for a in short_forms(abbr):
                    if len(a) >= 2:
                        inserts.append((code, a, "auto"))
                if code.startswith("0") and len(code.lstrip("0")) >= 3:
                    inserts.append((code, code.lstrip("0"), "auto"))

            manual = [
                ("000999", "999", "manual"),
                ("000999", "三九", "manual"),
                ("002275", "三金", "manual"),
                ("000538", "云南制药", "manual"),
            ]

            cur.executemany(
                """
                INSERT INTO company_alias(stock_code, alias, source)
                VALUES (%s,%s,%s)
                ON DUPLICATE KEY UPDATE source=VALUES(source)
                """,
                inserts + manual,
            )
            cur.execute("SELECT COUNT(*) c FROM company_alias")
            cnt = cur.fetchone()["c"]
            print(f"company_alias rows={cnt}")

        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
