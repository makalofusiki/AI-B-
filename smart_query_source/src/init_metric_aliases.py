from __future__ import annotations

import pymysql

from config import DB_CONFIG


ALIASES = [
    ("营业收入", "营业总收入", "income_sheet", "total_operating_revenue", "万元"),
    ("销售额", "营业总收入", "income_sheet", "total_operating_revenue", "万元"),
    ("营收", "营业总收入", "income_sheet", "total_operating_revenue", "万元"),
    ("利润", "净利润", "income_sheet", "net_profit", "万元"),
    ("短期借款", "短期借款", "balance_sheet", "liability_short_term_loans", "万元"),
    ("货币资金", "货币资金", "balance_sheet", "asset_cash_and_cash_equivalents", "万元"),
    ("存货", "存货", "balance_sheet", "asset_inventory", "万元"),
    ("应收账款", "应收账款", "balance_sheet", "asset_accounts_receivable", "万元"),
    ("股东权益", "股东权益", "balance_sheet", "equity_total_equity", "万元"),
    ("经营性现金流净额", "经营性现金流量净额", "cash_flow_sheet", "operating_cf_net_amount", "万元"),
    ("经营活动现金流净额", "经营性现金流量净额", "cash_flow_sheet", "operating_cf_net_amount", "万元"),
    ("投资性现金流净额", "投资性现金流量净额", "cash_flow_sheet", "investing_cf_net_amount", "万元"),
    ("投资现金流净额", "投资性现金流量净额", "cash_flow_sheet", "investing_cf_net_amount", "万元"),
    ("筹资性现金流净额", "筹资性现金流量净额", "cash_flow_sheet", "financing_cf_net_amount", "万元"),
    ("研发投入", "研发费用", "income_sheet", "operating_expense_rnd_expenses", "万元"),
    ("核心利润", "扣非净利润", "core_performance_indicators_sheet", "net_profit_excl_non_recurring", "万元"),
    ("扣非净利润", "扣非净利润", "core_performance_indicators_sheet", "net_profit_excl_non_recurring", "万元"),
    ("加权平均净资产收益率（扣非）", "加权平均净资产收益率（扣非）", "core_performance_indicators_sheet", "roe_weighted_excl_non_recurring", "%"),
    ("扣非加权平均净资产收益率", "加权平均净资产收益率（扣非）", "core_performance_indicators_sheet", "roe_weighted_excl_non_recurring", "%"),
    ("扣非ROE", "加权平均净资产收益率（扣非）", "core_performance_indicators_sheet", "roe_weighted_excl_non_recurring", "%"),
    ("存货周转率", "存货周转率", "__derived__", "inventory_turnover_ratio", "次"),
    ("出口业务占比", "出口业务占比", "report_export_ratio", "export_ratio_pct", "%"),
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
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS report_export_ratio (
                  id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  stock_code VARCHAR(20) NOT NULL,
                  stock_abbr VARCHAR(100),
                  report_year INT NOT NULL,
                  report_period VARCHAR(20) NOT NULL,
                  export_ratio_pct DECIMAL(12,4),
                  source_file VARCHAR(700),
                  snippet TEXT,
                  UNIQUE KEY uk_code_period (stock_code, report_year, report_period),
                  KEY idx_period (report_year, report_period)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS metric_alias (
                  id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  alias VARCHAR(120) NOT NULL,
                  metric_cn_name VARCHAR(120) NOT NULL,
                  table_name VARCHAR(80) NOT NULL,
                  field_name VARCHAR(120) NOT NULL,
                  unit VARCHAR(20) DEFAULT '万元',
                  is_enabled TINYINT NOT NULL DEFAULT 1,
                  UNIQUE KEY uk_alias (alias)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """
            )
            for alias, metric_cn, table_name, field_name, unit in ALIASES:
                cur.execute(
                    """
                    INSERT INTO metric_alias(alias, metric_cn_name, table_name, field_name, unit, is_enabled)
                    VALUES(%s,%s,%s,%s,%s,1)
                    ON DUPLICATE KEY UPDATE
                      metric_cn_name=VALUES(metric_cn_name),
                      table_name=VALUES(table_name),
                      field_name=VALUES(field_name),
                      unit=VALUES(unit),
                      is_enabled=1
                    """,
                    (alias, metric_cn, table_name, field_name, unit),
                )
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM metric_alias WHERE is_enabled=1")
            print(f"metric_alias enabled={cur.fetchone()['c']}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
