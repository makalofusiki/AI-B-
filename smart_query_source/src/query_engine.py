from __future__ import annotations

import os
import re
import logging
from typing import Optional, Tuple, Dict, Any, List

from charting import save_bar_chart
from config import LLM_CONFIG
from llm_client import LLMClient
from metric_mapping import METRIC_MAP, PERIOD_MAP

logger = logging.getLogger(__name__)


class QueryEngine:
    def __init__(self, db, result_dir: str):
        self.db = db
        self.result_dir = result_dir
        self.llm = LLMClient(LLM_CONFIG)
        self._company_aliases, self._company_by_code = self._build_company_index()
        self._metric_aliases = self._build_metric_aliases()

    def _normalize_text(self, s: str) -> str:
        return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", (s or "").upper())

    def _abbr_short_forms(self, abbr: str) -> List[str]:
        suffixes = [
            "股份",
            "药业",
            "制药",
            "医药",
            "生物",
            "集团",
            "科技",
            "健康",
            "中药",
            "藏药",
        ]
        forms = set()
        forms.add(abbr)
        for suf in suffixes:
            if abbr.endswith(suf):
                v = abbr[: -len(suf)]
                if len(v) >= 2:
                    forms.add(v)
        return list(forms)

    def _build_company_index(self):
        try:
            rows = self.db.fetch_all(
                """
                SELECT stock_code, stock_abbr, company_name
                FROM listed_company_basic_info
                """
            )
        except Exception:
            # If the table doesn't exist or DB is empty, return empty structures
            rows = []

        company_by_code = {}
        alias_items = []
        for r in rows:
            code_raw = str(r.get("stock_code") or "").strip()
            code_norm = code_raw.zfill(6) if code_raw.isdigit() else code_raw
            record = {
                "stock_code": code_norm,
                "stock_abbr": r.get("stock_abbr"),
                "company_name": r.get("company_name"),
            }
            if code_norm:
                company_by_code[code_norm] = record
                if code_norm.startswith("0"):
                    company_by_code[code_norm.lstrip("0")] = record

            aliases = set()
            abbr = (r.get("stock_abbr") or "").strip()
            cname = (r.get("company_name") or "").strip()
            if abbr:
                aliases.update(self._abbr_short_forms(abbr))
            if cname:
                aliases.add(cname)

            for a in aliases:
                na = self._normalize_text(a)
                if len(na) >= 2:
                    alias_items.append((na, record))

        # load db aliases if present
        try:
            db_alias_rows = self.db.fetch_all(
                "SELECT alias, stock_code FROM company_alias"
            )
            for a in db_alias_rows:
                alias = self._normalize_text(str(a.get("alias") or ""))
                code_raw = str(a.get("stock_code") or "").strip()
                code_norm = code_raw.zfill(6) if code_raw.isdigit() else code_raw
                rec = company_by_code.get(code_norm) or company_by_code.get(
                    code_norm.lstrip("0")
                )
                if alias and rec:
                    alias_items.append((alias, rec))
        except Exception:
            pass

        # manual aliases for common short references
        manual = {
            "999": "000999",
            "三九": "000999",
            "三金": "002275",
            "云南制药": "000538",
            "康芝": "300086",
            "康芝药业": "300086",
        }
        for alias, code in manual.items():
            rec = company_by_code.get(code) or company_by_code.get(code.lstrip("0"))
            if rec:
                alias_items.append((self._normalize_text(alias), rec))

        # deduplicate (alias, stock_code)
        uniq = {}
        for a, rec in alias_items:
            k = (a, rec["stock_code"])
            uniq[k] = (a, rec)
        return list(uniq.values()), company_by_code

    def _build_metric_aliases(self) -> List[Tuple[str, Tuple[str, str, str, str]]]:
        aliases: Dict[str, Tuple[str, str, str, str]] = {}
        for cn_name, (table_name, field_name, unit) in METRIC_MAP.items():
            aliases[cn_name] = (cn_name, table_name, field_name, unit)
        try:
            rows = self.db.fetch_all(
                """
                SELECT alias, metric_cn_name, table_name, field_name, unit
                FROM metric_alias
                WHERE is_enabled=1
                """
            )
            for r in rows:
                alias = str(r.get("alias") or "").strip()
                metric_cn = str(r.get("metric_cn_name") or "").strip()
                table_name = str(r.get("table_name") or "").strip()
                field_name = str(r.get("field_name") or "").strip()
                unit = str(r.get("unit") or "").strip()
                if alias and metric_cn and table_name and field_name:
                    aliases[alias] = (metric_cn, table_name, field_name, unit or "万元")
        except Exception:
            pass
        return sorted(aliases.items(), key=lambda x: len(x[0]), reverse=True)

    def _metric_from_alias(self, alias: str) -> Optional[Tuple[str, str, str, str]]:
        a = str(alias or "").strip()
        if not a:
            return None
        for k, metric in self._metric_aliases:
            if k == a:
                return metric
        for k, metric in self._metric_aliases:
            if k and (k in a or a in k):
                return metric
        return None

    def _company_from_llm(
        self, company_name: str, stock_code: str
    ) -> Optional[Dict[str, Any]]:
        code = str(stock_code or "").strip()
        if code and code.isdigit():
            c = code.zfill(6)
            rec = self._company_by_code.get(c) or self._company_by_code.get(code)
            if rec:
                return rec
        name = str(company_name or "").strip()
        if name:
            rec, cands = self._find_company(name)
            if rec:
                return rec
            if len(cands) == 1:
                return cands[0]
        return None

    def _apply_llm_slot_fallback(
        self,
        question: str,
        metric,
        company,
        year,
        period,
        topn,
        is_collection,
    ):
        if not self.llm.enabled:
            return metric, company, year, period, topn, is_collection
        slots = self.llm.parse_slots(question) or {}
        if metric is None:
            metric = self._metric_from_alias(slots.get("metric_alias"))
        if company is None:
            company = self._company_from_llm(
                slots.get("company_name"), slots.get("stock_code")
            )
        if year is None:
            y = slots.get("year")
            if isinstance(y, int):
                year = y
            elif isinstance(y, str) and y.isdigit():
                year = int(y)
        if period in (None, "", "FY"):
            p = str(slots.get("period") or "").upper()
            if p in {"Q1", "HY", "Q3", "FY"}:
                period = p
        if topn is None:
            n = slots.get("topn")
            if isinstance(n, int) and 1 <= n <= 100:
                topn = n
            elif isinstance(n, str) and n.isdigit():
                ni = int(n)
                if 1 <= ni <= 100:
                    topn = ni
        if not is_collection:
            b = slots.get("is_collection")
            if isinstance(b, bool):
                is_collection = b
        return metric, company, year, period, topn, is_collection

    def _polish_analysis_with_ai(self, question: str, analysis: str, rows):
        if not self.llm.enabled:
            return analysis
        if not rows:
            return analysis
        ai = self.llm.generate_answer(question, analysis, rows)
        return ai or analysis

    def _period_fallback_order(self, period: str) -> List[str]:
        p = period or "FY"
        if p == "Q3":
            return ["Q3", "HY", "FY"]
        if p == "HY":
            return ["HY", "FY"]
        if p == "Q1":
            return ["Q1", "HY", "FY"]
        return [p]

    def _best_period_for_company_metric(
        self,
        stock_code: str,
        year: int,
        table_name: str,
        field_name: str,
        default_period: str,
    ) -> str:
        try:
            sql = f"""
            SELECT report_period
            FROM {table_name}
            WHERE LPAD(stock_code,6,'0')=%s
              AND report_year=%s
              AND {field_name} IS NOT NULL
            ORDER BY FIELD(report_period,'Q3','HY','Q1','FY')
            LIMIT 1
            """
            row = self.db.fetch_one(sql, (str(stock_code).zfill(6), year))
            if row and row.get("report_period"):
                return row["report_period"]
        except Exception:
            pass
        return default_period

    def _ai_retry_decision(
        self,
        question: str,
        year: Optional[int],
        period: str,
        has_threshold: bool,
        metric_hint: str = "",
    ):
        if not self.llm.enabled:
            return {}
        d = (
            self.llm.suggest_retry_strategy(
                question, year, period, has_threshold, metric_hint=metric_hint
            )
            or {}
        )
        if not isinstance(d, dict):
            return {}
        out = {}
        fp = str(d.get("fallback_period") or "").upper()
        if fp in {"Q3", "HY", "FY"}:
            out["fallback_period"] = fp
        if isinstance(d.get("drop_threshold"), bool):
            out["drop_threshold"] = d["drop_threshold"]
        tn = d.get("topn")
        if isinstance(tn, int) and 1 <= tn <= 100:
            out["topn"] = tn
        elif isinstance(tn, str) and tn.isdigit():
            ti = int(tn)
            if 1 <= ti <= 100:
                out["topn"] = ti
        alt = str(d.get("alternate_metric_alias") or "").strip()
        if alt:
            out["alternate_metric_alias"] = alt
        return out

    def _build_chart_intro(
        self,
        year: int,
        period: str,
        metric_cn: str,
        unit: str,
        rows: List[Dict[str, Any]],
        topn: int,
    ) -> str:
        if not rows:
            return "未查询到符合条件的数据。"
        vals = []
        for r in rows:
            try:
                vals.append(float(r.get("metric_value", 0) or 0))
            except Exception:
                vals.append(0.0)
        pairs = list(zip(rows, vals))
        pairs = sorted(pairs, key=lambda x: x[1], reverse=True)
        top3 = pairs[:3]
        top3_text = "、".join(
            [f"{r.get('stock_abbr', '')}（{v:,.2f}{unit}）" for r, v in top3]
        )
        max_v = max(vals) if vals else 0.0
        min_v = min(vals) if vals else 0.0
        avg_v = (sum(vals) / len(vals)) if vals else 0.0
        return (
            f"{year}年{period}{metric_cn}已生成柱状图（Top{topn}）。"
            f"横轴为公司简称，纵轴为{metric_cn}（{unit}）。"
            f"前三为：{top3_text}。"
            f"样本区间：{min_v:,.2f}{unit}~{max_v:,.2f}{unit}，均值约{avg_v:,.2f}{unit}。"
        )

    def _extract_metric(self, question: str) -> Optional[Tuple[str, str, str, str]]:
        for alias, metric in self._metric_aliases:
            if alias and alias in (question or ""):
                return metric
        # ratio-like wording fallback: e.g. "研发费用占比"
        ratio_patterns = [
            ("研发费用占比", "研发费用"),
            ("销售费用占比", "销售费用"),
            ("管理费用占比", "管理费用"),
            ("营业成本占比", "营业成本"),
        ]
        q = question or ""
        for p, base_metric in ratio_patterns:
            if p in q and base_metric in METRIC_MAP:
                t, f, u = METRIC_MAP[base_metric]
                return base_metric, t, f, u
        if "亏钱" in question or "亏损" in question:
            return (
                "扣非净利润",
                "core_performance_indicators_sheet",
                "net_profit_excl_non_recurring",
                "万元",
            )
        return None

    def _extract_year(self, question: str) -> Optional[int]:
        m = re.search(r"(20\d{2})年", question)
        if m:
            return int(m.group(1))
        if "去年" in (question or ""):
            return -1
        if "今年" in (question or ""):
            return -2
        return None

    def _extract_period(self, question: str) -> Optional[str]:
        if "前三季度" in (question or ""):
            return "Q3"
        for k, v in PERIOD_MAP.items():
            if k in question:
                return v
        return None

    def _extract_topn(self, question: str) -> Optional[int]:
        m = re.search(r"(?:top|TOP|前)\s*(\d+)", question)
        if m:
            return int(m.group(1))
        m2 = re.search(
            r"(?:前|最高的|最低的)\s*([一二三四五六七八九十两\d]+)", question or ""
        )
        if m2:
            token = m2.group(1)
            if token.isdigit():
                return int(token)
            cn_num = {
                "一": 1,
                "二": 2,
                "两": 2,
                "三": 3,
                "四": 4,
                "五": 5,
                "六": 6,
                "七": 7,
                "八": 8,
                "九": 9,
                "十": 10,
            }
            if token in cn_num:
                return cn_num[token]
        return None

    def _is_collection_query(self, question: str) -> bool:
        keys = [
            "统计",
            "哪些",
            "有多少",
            "多少家",
            "数量",
            "排名",
            "前",
            "超过",
            "超",
            "低于",
            "不足",
            "高于",
            "大于",
            "小于",
            "top",
            "TOP",
            "所有上市公司",
            "全部公司",
            "这些公司",
            "各公司",
            "每家公司",
            "66家",
            "均值",
            "平均",
            "分布",
            "最高",
            "最低",
            "找出",
            "筛选",
            "上市企业",
        ]
        return any(k in (question or "") for k in keys)

    def _has_broad_company_scope(self, question: str) -> bool:
        q = question or ""
        keys = [
            "所有上市公司",
            "全部公司",
            "这些公司",
            "各公司",
            "每家公司",
            "66家",
            "行业",
            "中药公司",
            "中药企业",
            "上市企业",
            "企业有哪些",
            "相关性",
            "分组",
            "分为",
            "共同点",
        ]
        return any(k in q for k in keys)

    def _extract_threshold(self, question: str):
        q = question or ""
        op = None
        if "超过" in q or "大于" in q or "高于" in q or "超" in q:
            op = ">"
        elif "低于" in q or "小于" in q or "不足" in q:
            op = "<"
        if not op:
            return None
        m = re.search(
            r"(?:超过|大于|高于|低于|小于|超|不足)\s*([0-9]+(?:\.[0-9]+)?)\s*(亿元|万元|%|元)?",
            q,
        )
        if not m:
            return None
        v = float(m.group(1))
        unit = m.group(2) or ""
        # DB amount fields are mostly 万元
        if unit == "亿元":
            v *= 10000.0
        if unit == "元":
            v /= 10000.0
        return op, v

    def _extract_special_condition(self, question: str, field_name: str):
        q = question or ""
        if ("亏钱" in q or "亏损" in q) and field_name in (
            "net_profit",
            "net_profit_excl_non_recurring",
        ):
            return f"{field_name} < 0", "核心利润为负"
        if "为负" in q and field_name in (
            "net_profit",
            "net_profit_excl_non_recurring",
            "operating_cf_net_amount",
            "investing_cf_net_amount",
            "financing_cf_net_amount",
        ):
            return f"{field_name} < 0", f"{field_name}为负"
        if "为正" in q and field_name in (
            "net_profit",
            "net_profit_excl_non_recurring",
            "operating_cf_net_amount",
            "investing_cf_net_amount",
            "financing_cf_net_amount",
        ):
            return f"{field_name} > 0", f"{field_name}为正"
        return None, ""

    def _extract_metric_comparison(self, question: str):
        q = question or ""
        op = None
        op_kw = None
        if "超过" in q:
            op = ">"
            op_kw = "超过"
        elif "大于" in q:
            op = ">"
            op_kw = "大于"
        elif "高于" in q:
            op = ">"
            op_kw = "高于"
        elif "低于" in q:
            op = "<"
            op_kw = "低于"
        elif "小于" in q:
            op = "<"
            op_kw = "小于"
        if not op:
            return None

        op_pos = q.find(op_kw) if op_kw else -1
        if op_pos < 0:
            return None
        found = []
        for alias, metric in self._metric_aliases:
            pos = q.find(alias)
            if pos >= 0:
                found.append((pos, alias, metric))
        if len(found) < 2:
            return None
        left_candidates = [x for x in found if x[0] < op_pos]
        right_candidates = [x for x in found if x[0] > op_pos]
        if not left_candidates or not right_candidates:
            return None
        left = sorted(left_candidates, key=lambda x: x[0], reverse=True)[0][2]
        right = sorted(right_candidates, key=lambda x: x[0])[0][2]
        if left[1] != right[1]:
            return None
        return left, right, op

    def _is_open_analysis_question(self, question: str) -> bool:
        q = question or ""
        keys = [
            "医保目录",
            "北向资金",
            "共同点",
            "资产重组",
            "供应链",
            "新品上市周期",
            "价格波动趋势",
            "影响力",
            "判断依据",
        ]
        return any(k in q for k in keys)

    def _extract_possible_company_name(self, question: str) -> Optional[str]:
        q = question or ""
        m = re.search(r"([\u4e00-\u9fa5]{2,}(?:股份|药业|制药|集团))", q)
        return m.group(1) if m else None

    def _is_yoy_question(self, question: str) -> bool:
        q = question or ""
        return ("同比增长率" in q) or ("同比" in q and "增长" in q)

    def _is_change_trend_question(self, question: str) -> bool:
        q = question or ""
        change_keywords = [
            "变化",
            "变化趋势",
            "趋势",
            "变动",
            "波动",
            "变化情况",
            "变化了多少",
            "变化幅度",
            "增减变化",
            "增长变化",
            "下降变化",
            "近三年",
            "近两年",
            "近年来",
            "历年",
            "历史变化",
            "多年变化",
            "连续变化",
            "变化分析",
            "变化原因",
            "增减",
        ]
        return any(kw in q for kw in change_keywords)

    def _is_comparison_question(self, question: str) -> bool:
        q = question or ""
        comparison_keywords = [
            "对比",
            "比较",
            "差异",
            "差别",
            "区别",
            "和...比",
            "与...比",
            "相比",
            "相较",
            "高于",
            "低于",
            "优于",
            "差于",
            "比...高",
            "比...低",
            "比...多",
            "比...少",
            "同步增长",
            "增速对比",
            "高低对比",
        ]
        return any(kw in q for kw in comparison_keywords)

    def _resolve_max_year(self, table_name: str, period: str):
        if table_name == "__derived__":
            row = self.db.fetch_one(
                "SELECT MAX(report_year) AS y FROM balance_sheet WHERE report_period=%s",
                (period,),
            )
            return row["y"] if row else None
        row = self.db.fetch_one(f"SELECT MAX(report_year) AS y FROM {table_name}")
        return row["y"] if row else None

    def _find_by_company_name_condition(self, question: str) -> List[Dict[str, Any]]:
        q = question or ""
        patterns = [
            r"(?:企业名称|公司名称|公司名)\s*[：:]\s*([0-9A-Za-z\u4e00-\u9fff]+)",
            r"(?:企业名称|公司名称|公司名).{0,8}(?:包含|含有|带有|中含)\s*([0-9A-Za-z\u4e00-\u9fff]+)",
        ]
        keyword = None
        for p in patterns:
            m = re.search(p, q)
            if m:
                keyword = m.group(1).strip()
                break
        if not keyword:
            return []

        sql = """
        SELECT stock_code, stock_abbr, company_name
        FROM listed_company_basic_info
        WHERE stock_abbr LIKE CONCAT('%%', %s, '%%')
           OR company_name LIKE CONCAT('%%', %s, '%%')
        ORDER BY CHAR_LENGTH(stock_abbr) DESC
        LIMIT 20
        """
        rows = self.db.fetch_all(sql, (keyword, keyword))
        out = []
        for r in rows:
            code_raw = str(r.get("stock_code") or "").strip()
            code_norm = code_raw.zfill(6) if code_raw.isdigit() else code_raw
            out.append(
                {
                    "stock_code": code_norm,
                    "stock_abbr": r.get("stock_abbr"),
                    "company_name": r.get("company_name"),
                }
            )
        return out

    def _find_company(
        self, question: str
    ) -> tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        # 0) explicit company-name-condition search
        by_condition = self._find_by_company_name_condition(question)
        if len(by_condition) == 1:
            return by_condition[0], by_condition
        if len(by_condition) > 1:
            return None, by_condition

        # 1) stock code direct match: supports 3-6 digit inputs like 999
        nums = re.findall(r"(?<!\d)(\d{3,6})(?!\d)", question or "")
        for n in nums:
            code = n.zfill(6)
            rec = self._company_by_code.get(code) or self._company_by_code.get(n)
            if rec:
                return rec, [rec]

        # 2) alias/abbr/name match
        qn = self._normalize_text(question or "")
        if not qn:
            return None, []
        best = None
        best_score = -1
        for alias, rec in self._company_aliases:
            if alias and alias in qn:
                score = len(alias)
                if qn == alias:
                    score += 100
                if score > best_score:
                    best_score = score
                    best = rec
        if best:
            return best, [best]
        return None, []

    def _need_clarification(
        self,
        metric,
        company,
        topn,
        company_candidates: List[Dict[str, Any]],
        is_collection: bool,
    ) -> Optional[str]:
        if metric is None:
            return "请明确要查询的指标，例如：净利润、利润总额、营业总收入、总资产等。"
        if company is None and len(company_candidates) > 1:
            cands = "、".join([c["stock_abbr"] for c in company_candidates[:5]])
            return f"公司名称条件匹配到多个公司：{cands}。请明确具体公司。"
        if company is None and topn is None and not is_collection:
            return "请明确公司名称，或说明是TopN类问题（例如：2024年利润总额前10名）。"
        return None

    def _need_clarification_with_question(
        self,
        question: str,
        metric,
        company,
        topn,
        company_candidates: List[Dict[str, Any]],
        is_collection: bool,
    ) -> Optional[str]:
        if metric is None:
            if self._is_open_analysis_question(question):
                return None
            return "请明确要查询的指标，例如：净利润、利润总额、营业总收入、总资产等。"
        if company is None and len(company_candidates) > 1:
            cands = "、".join([c["stock_abbr"] for c in company_candidates[:5]])
            return f"公司名称条件匹配到多个公司：{cands}。请明确具体公司。"
        if (
            company is None
            and topn is None
            and not is_collection
            and not self._has_broad_company_scope(question)
        ):
            if "公司" in (question or "") or "企业" in (question or ""):
                return None
            return "请明确公司名称，或说明是TopN类问题（例如：2024年利润总额前10名）。"
        return None

    def _answer_collection(
        self,
        question_id: str,
        turn_index: int,
        question: str,
        metric,
        year,
        period,
        topn,
    ):
        metric_cn, table_name, field_name, unit = metric
        max_year = self._resolve_max_year(table_name, period)
        if year == -1 and max_year is not None:
            year = max_year - 1
        elif year == -2 and max_year is not None:
            year = max_year
        elif year is None:
            year = max_year
        if year is None:
            return {
                "question_id": question_id,
                "turn_index": turn_index,
                "question": question,
                "status": "need_clarification",
                "clarification": f"当前{table_name}尚无已入库数据，请先导入核心财务数据后再查询。",
                "sql": "",
                "result": [],
                "analysis": "",
                "charts": [],
                "context_update": {},
            }

        if table_name == "__derived__" and field_name == "inventory_turnover_ratio":
            if topn is None:
                topn = 10
            sql = """
            SELECT b.stock_code, b.stock_abbr,
                   CASE WHEN b.asset_inventory IS NULL OR b.asset_inventory=0 THEN NULL
                        ELSE i.operating_expense_cost_of_sales / b.asset_inventory END AS metric_value
            FROM balance_sheet b
            JOIN income_sheet i
              ON LPAD(i.stock_code,6,'0')=LPAD(b.stock_code,6,'0')
             AND i.report_year=b.report_year
             AND i.report_period=b.report_period
            WHERE b.report_year=%s
              AND b.report_period=%s
              AND b.asset_inventory IS NOT NULL
              AND b.asset_inventory<>0
              AND i.operating_expense_cost_of_sales IS NOT NULL
            ORDER BY metric_value DESC
            LIMIT %s
            """
            rows = self.db.fetch_all(sql, (year, period, topn))
            used_period = period
            if not rows:
                for p2 in self._period_fallback_order(period):
                    if p2 == period:
                        continue
                    rows = self.db.fetch_all(sql, (year, p2, topn))
                    if rows:
                        used_period = p2
                        break
            chart_path = os.path.join(
                self.result_dir, f"{question_id}_{turn_index}.jpg"
            )
            if rows:
                save_bar_chart(
                    rows,
                    "stock_abbr",
                    "metric_value",
                    f"{year}{used_period} 存货周转率 Top{topn}",
                    chart_path,
                )
                charts = [chart_path]
                analysis = self._build_chart_intro(
                    year, used_period, "存货周转率", "次", rows, topn
                )
            else:
                charts = []
                analysis = "未查询到符合条件的数据。"
            analysis = self._polish_analysis_with_ai(question, analysis, rows)
            return {
                "question_id": question_id,
                "turn_index": turn_index,
                "question": question,
                "status": "ok",
                "clarification": "",
                "sql": " ".join(sql.split()),
                "result": rows,
                "analysis": analysis,
                "charts": charts,
                "context_update": {
                    "metric": metric,
                    "year": year,
                    "period": used_period,
                    "is_collection": True,
                },
            }

        if self._is_yoy_question(question) and table_name != "__derived__":
            if topn is None:
                topn = 10
            sql = f"""
            SELECT t1.stock_code, t1.stock_abbr,
                   t1.{field_name} AS current_value,
                   t0.{field_name} AS previous_value,
                   CASE WHEN t0.{field_name}=0 THEN NULL
                        ELSE (t1.{field_name}-t0.{field_name})/t0.{field_name}*100 END AS yoy_growth_rate
            FROM {table_name} t1
            JOIN {table_name} t0
              ON LPAD(t0.stock_code,6,'0')=LPAD(t1.stock_code,6,'0')
             AND t0.report_period=t1.report_period
             AND t0.report_year=t1.report_year-1
            WHERE t1.report_year=%s
              AND t1.report_period=%s
              AND t1.{field_name} IS NOT NULL
              AND t0.{field_name} IS NOT NULL
            ORDER BY yoy_growth_rate DESC
            LIMIT %s
            """
            rows = self.db.fetch_all(sql, (year, period, topn))
            used_period = period
            if not rows:
                for p2 in self._period_fallback_order(period):
                    if p2 == period:
                        continue
                    rows = self.db.fetch_all(sql, (year, p2, topn))
                    if rows:
                        used_period = p2
                        break
            analysis = f"{year}年{used_period}{metric_cn}同比增长率前{topn}家公司已返回（同比公式：(当期-上年同期)/上年同期*100）。"
            analysis = self._polish_analysis_with_ai(
                question, analysis if rows else "未查询到符合条件的数据。", rows
            )
            return {
                "question_id": question_id,
                "turn_index": turn_index,
                "question": question,
                "status": "ok",
                "clarification": "",
                "sql": " ".join(sql.split()),
                "result": rows,
                "analysis": analysis,
                "charts": [],
                "context_update": {
                    "metric": metric,
                    "year": year,
                    "period": used_period,
                    "is_collection": True,
                },
            }

        if self._is_change_trend_question(question) and table_name != "__derived__":
            if topn is None:
                topn = 10
            sql = f"""
            SELECT t1.stock_code, t1.stock_abbr,
                   t1.{field_name} AS current_value,
                   t0.{field_name} AS previous_value,
                   CASE WHEN t0.{field_name}=0 THEN NULL
                        ELSE (t1.{field_name}-t0.{field_name})/t0.{field_name}*100 END AS yoy_growth_rate,
                   CASE WHEN t0.{field_name}=0 THEN NULL
                        ELSE (t1.{field_name}-t0.{field_name}) END AS abs_change
            FROM {table_name} t1
            JOIN {table_name} t0
              ON LPAD(t0.stock_code,6,'0')=LPAD(t1.stock_code,6,'0')
             AND t0.report_period=t1.report_period
             AND t0.report_year=t1.report_year-1
            WHERE t1.report_year=%s
              AND t1.report_period=%s
              AND t1.{field_name} IS NOT NULL
              AND t0.{field_name} IS NOT NULL
            ORDER BY yoy_growth_rate DESC
            LIMIT %s
            """
            rows = self.db.fetch_all(sql, (year, period, topn))
            used_period = period
            if not rows:
                for p2 in self._period_fallback_order(period):
                    if p2 == period:
                        continue
                    rows = self.db.fetch_all(sql, (year, p2, topn))
                    if rows:
                        used_period = p2
                        break
            if rows:
                top_change = rows[0]
                change_rate = top_change.get("yoy_growth_rate")
                change_abs = top_change.get("abs_change")
                if change_rate is not None:
                    direction = "增长" if float(change_rate) > 0 else "下降"
                    analysis = (
                        f"{year}年{used_period}{metric_cn}变化趋势已返回前{topn}家公司。"
                        f"其中{top_change['stock_abbr']}变化趋势最大："
                        f"{direction}{abs(float(change_rate)):.2f}%，"
                        f"绝对变化量{float(change_abs):+,.2f}{unit}。"
                    )
                else:
                    analysis = f"{year}年{used_period}{metric_cn}变化趋势已返回前{topn}家公司。"
            else:
                fallback_sql = f"""
                SELECT stock_code, stock_abbr, {field_name} AS metric_value
                FROM {table_name}
                WHERE report_year=%s AND report_period=%s AND {field_name} IS NOT NULL
                ORDER BY {field_name} DESC
                LIMIT %s
                """
                rows = self.db.fetch_all(fallback_sql, (year, period, topn))
                if rows:
                    analysis = (
                        f"未查询到{year}年{period}{metric_cn}的同比变化数据。"
                        f"当前数据已返回同期数值前{topn}家公司供参考。"
                    )
                else:
                    analysis = "未查询到符合条件的数据。"
            analysis = self._polish_analysis_with_ai(question, analysis, rows)
            return {
                "question_id": question_id,
                "turn_index": turn_index,
                "question": question,
                "status": "ok",
                "clarification": "",
                "sql": " ".join(sql.split()),
                "result": rows,
                "analysis": analysis,
                "charts": [],
                "context_update": {
                    "metric": metric,
                    "year": year,
                    "period": used_period,
                    "is_collection": True,
                },
            }

        threshold = self._extract_threshold(question)
        compare = self._extract_metric_comparison(question)
        extra_cond, extra_desc = self._extract_special_condition(question, field_name)
        where = [f"report_year=%s", f"report_period=%s", f"{field_name} IS NOT NULL"]
        params = [year, period]
        threshold_cond = None
        compare_sql_select = None
        compare_desc = ""
        compare_table = table_name
        compare_order_field = field_name
        compare_where = None
        if compare:
            left, right, op2 = compare
            _, l_table, l_field, _ = left
            _, r_table, r_field, _ = right
            if l_table == r_table:
                compare_table = l_table
                compare_where = [
                    f"report_year=%s",
                    f"report_period=%s",
                    f"{l_field} IS NOT NULL",
                    f"{r_field} IS NOT NULL",
                    f"{l_field} {op2} {r_field}",
                ]
                params = [year, period]
                compare_desc = f"{left[0]}{op2}{right[0]}"
                compare_order_field = "diff_value"
        if threshold:
            op, value = threshold
            threshold_cond = f"{field_name} {op} %s"
            where.append(threshold_cond)
            if compare_where is not None:
                compare_where.append(threshold_cond)
            params.append(value)
        if extra_cond:
            where.append(extra_cond)
            if compare_where is not None:
                compare_where.append(extra_cond)
        if compare_where is not None:
            compare_sql_select = (
                f"SELECT stock_code, stock_abbr, {l_field} AS left_metric_value, {r_field} AS right_metric_value, "
                f"({l_field}-{r_field}) AS diff_value FROM {compare_table} WHERE {' AND '.join(compare_where)}"
            )

        if topn is None:
            if (
                "有多少" in (question or "")
                or "多少家" in (question or "")
                or "数量" in (question or "")
                or "统计" in (question or "")
            ):
                if compare_sql_select:
                    sql = f"SELECT COUNT(DISTINCT stock_code) AS company_count FROM ({compare_sql_select}) x"
                    rows = self.db.fetch_all(sql, tuple(params))
                    c = rows[0]["company_count"] if rows else 0
                    analysis = (
                        f"{year}年{period}满足条件（{compare_desc}）的公司数量为{c}家。"
                    )
                    analysis = self._polish_analysis_with_ai(question, analysis, rows)
                    return {
                        "question_id": question_id,
                        "turn_index": turn_index,
                        "question": question,
                        "status": "ok",
                        "clarification": "",
                        "sql": " ".join(sql.split()),
                        "result": rows,
                        "analysis": analysis,
                        "charts": [],
                        "context_update": {
                            "metric": metric,
                            "year": year,
                            "period": period,
                            "is_collection": True,
                        },
                    }
                sql = f"SELECT COUNT(DISTINCT stock_code) AS company_count FROM {table_name} WHERE {' AND '.join(where)}"
                rows = self.db.fetch_all(sql, tuple(params))
                c = rows[0]["company_count"] if rows else 0
                if c == 0:
                    strategy = self._ai_retry_decision(
                        question, year, period, bool(threshold), metric_hint=metric_cn
                    )
                    period_try = strategy.get("fallback_period")
                    drop_threshold = strategy.get("drop_threshold", False)
                    where2 = list(where)
                    params2 = list(params)
                    if period_try and period_try != period:
                        params2[1] = period_try
                    if drop_threshold and threshold_cond and threshold_cond in where2:
                        where2.remove(threshold_cond)
                        if len(params2) > 2:
                            params2 = params2[:-1]
                    sql2 = f"SELECT COUNT(DISTINCT stock_code) AS company_count FROM {table_name} WHERE {' AND '.join(where2)}"
                    rows2 = self.db.fetch_all(sql2, tuple(params2))
                    c2 = rows2[0]["company_count"] if rows2 else 0
                    if c2 > 0:
                        rows = rows2
                        c = c2
                        sql = sql2
                        if period_try and period_try != period:
                            period = period_try
                analysis = f"{year}年{period}满足条件的公司数量为{c}家。"
                analysis = self._polish_analysis_with_ai(question, analysis, rows)
                return {
                    "question_id": question_id,
                    "turn_index": turn_index,
                    "question": question,
                    "status": "ok",
                    "clarification": "",
                    "sql": " ".join(sql.split()),
                    "result": rows,
                    "analysis": analysis,
                    "charts": [],
                    "context_update": {
                        "metric": metric,
                        "year": year,
                        "period": period,
                        "is_collection": True,
                    },
                }
            topn = 10

        if compare_sql_select:
            sql = f"{compare_sql_select} ORDER BY {compare_order_field} DESC LIMIT %s"
            params2 = params + [topn]
        else:
            sql = f"""
            SELECT stock_code, stock_abbr, {field_name} AS metric_value
            FROM {table_name}
            WHERE {" AND ".join(where)}
            ORDER BY {field_name} DESC
            LIMIT %s
            """
            params2 = params + [topn]
        rows = self.db.fetch_all(sql, tuple(params2))
        used_period = period
        if not rows:
            strategy = self._ai_retry_decision(
                question, year, period, bool(threshold), metric_hint=metric_cn
            )
            period_candidates = self._period_fallback_order(period)
            if (
                strategy.get("fallback_period")
                and strategy["fallback_period"] not in period_candidates
            ):
                period_candidates.append(strategy["fallback_period"])
            drop_threshold = strategy.get("drop_threshold", False)
            for p2 in period_candidates:
                if p2 == used_period:
                    continue
                params_try = list(params2)
                params_try[1] = p2
                rows_try = self.db.fetch_all(sql, tuple(params_try))
                if rows_try:
                    rows = rows_try
                    used_period = p2
                    params2 = params_try
                    break
            if (
                (not rows)
                and drop_threshold
                and threshold_cond
                and (not compare_sql_select)
            ):
                where2 = [w for w in where if w != threshold_cond]
                params_no_thr = [year, used_period, topn]
                sql_no_thr = f"""
                SELECT stock_code, stock_abbr, {field_name} AS metric_value
                FROM {table_name}
                WHERE {" AND ".join(where2)}
                ORDER BY {field_name} DESC
                LIMIT %s
                """
                rows_try = self.db.fetch_all(sql_no_thr, tuple(params_no_thr))
                if rows_try:
                    rows = rows_try
                    sql = sql_no_thr
                    params2 = params_no_thr
            if (not rows) and (not compare_sql_select):
                alt_alias = strategy.get("alternate_metric_alias")
                alt_metric = self._metric_from_alias(alt_alias) if alt_alias else None
                if alt_metric:
                    alt_cn, alt_table, alt_field, alt_unit = alt_metric
                    sql_alt = f"""
                    SELECT stock_code, stock_abbr, {alt_field} AS metric_value
                    FROM {alt_table}
                    WHERE report_year=%s AND report_period=%s AND {alt_field} IS NOT NULL
                    ORDER BY {alt_field} DESC
                    LIMIT %s
                    """
                    rows_try = self.db.fetch_all(sql_alt, (year, used_period, topn))
                    if rows_try:
                        rows = rows_try
                        sql = sql_alt
                        metric_cn, table_name, field_name, unit = (
                            alt_cn,
                            alt_table,
                            alt_field,
                            alt_unit,
                        )

        chart_path = os.path.join(self.result_dir, f"{question_id}_{turn_index}.jpg")
        if rows:
            if compare_sql_select:
                charts = []
                analysis = f"{year}年{used_period}满足条件（{compare_desc}）的公司前{topn}名已返回。"
            else:
                save_bar_chart(
                    rows,
                    "stock_abbr",
                    "metric_value",
                    f"{year}{used_period} {metric_cn} Top{topn}",
                    chart_path,
                )
                charts = [chart_path]
                analysis = self._build_chart_intro(
                    year, used_period, metric_cn, unit, rows, topn
                )
            if threshold:
                analysis = (
                    f"{year}年{used_period}中{metric_cn}{threshold[0]}{threshold[1]:.2f}{unit}的公司图表已生成。"
                    + (
                        " "
                        + self._build_chart_intro(
                            year, used_period, metric_cn, unit, rows, topn
                        )
                        if rows
                        else ""
                    )
                )
            if extra_desc:
                analysis += f"（条件：{extra_desc}）"
        else:
            charts = []
            analysis = "未查询到符合条件的数据。"
        analysis = self._polish_analysis_with_ai(question, analysis, rows)

        return {
            "question_id": question_id,
            "turn_index": turn_index,
            "question": question,
            "status": "ok",
            "clarification": "",
            "sql": " ".join(sql.split()),
            "result": rows,
            "analysis": analysis,
            "charts": charts,
            "context_update": {
                "metric": metric,
                "year": year,
                "period": used_period,
                "is_collection": True,
            },
        }

    def answer(
        self,
        question_id: str,
        question: str,
        context: Optional[Dict[str, Any]] = None,
        turn_index: int = 1,
    ) -> Dict[str, Any]:
        try:
            context = context or {}
            metric = self._extract_metric(question) or context.get("metric")
            year = self._extract_year(question) or context.get("year")
            period_from_q = self._extract_period(question)
            period = period_from_q or context.get("period") or "FY"
            topn = self._extract_topn(question)
            is_collection = (
                self._is_collection_query(question)
                or self._has_broad_company_scope(question)
                or bool(context.get("is_collection"))
            )
            company, company_candidates = self._find_company(question)
            # debug tracing for hard-to-find type errors
            try:
                print(f"[DEBUG] question_id={question_id} turn_index={turn_index}")
                print(f"[DEBUG] metric={metric} year={year} period_from_q={period_from_q} period={period} topn={topn} is_collection={is_collection}")
                print(f"[DEBUG] company={company} company_candidates_len={len(company_candidates)}")
            except Exception:
                pass
            company = company or context.get("company")
            if company is None and (
                "公司" in (question or "") or "企业" in (question or "")
            ):
                is_collection = True
            if company is None and not is_collection:
                unknown_company = self._extract_possible_company_name(question)
                if unknown_company:
                    return {
                        "question_id": question_id,
                        "turn_index": turn_index,
                        "question": question,
                        "status": "ok",
                        "clarification": "",
                        "sql": "",
                        "result": [],
                        "analysis": f"{unknown_company}不在当前66家中药上市公司样本范围内，无法直接给出该题的结构化财务结论。",
                        "charts": [],
                        "context_update": {},
                        "company_candidates": company_candidates,
                    }

            clarification = self._need_clarification_with_question(
                question,
                metric,
                company,
                topn,
                company_candidates,
                is_collection,
            )
            if clarification:
                metric, company, year, period, topn, is_collection = (
                    self._apply_llm_slot_fallback(
                        question, metric, company, year, period, topn, is_collection
                    )
                )
                clarification = self._need_clarification_with_question(
                    question,
                    metric,
                    company,
                    topn,
                    company_candidates,
                    is_collection,
                )
            if clarification:
                return {
                    "question_id": question_id,
                    "turn_index": turn_index,
                    "question": question,
                    "status": "need_clarification",
                    "clarification": clarification,
                    "sql": "",
                    "result": [],
                    "analysis": "",
                    "charts": [],
                    "context_update": {},
                    "company_candidates": company_candidates,
                }

            if metric is None and self._is_open_analysis_question(question):
                analysis = "该问题属于宏观/研报分析类，当前数据库主要提供财务与公告结构化数据。可先基于附件研报提取关键词标签（如风险类型、政策主题）后，再与财务指标做交叉查询。"
                analysis = self._polish_analysis_with_ai(question, analysis, [])
                return {
                    "question_id": question_id,
                    "turn_index": turn_index,
                    "question": question,
                    "status": "ok",
                    "clarification": "",
                    "sql": "",
                    "result": [],
                    "analysis": analysis,
                    "charts": [],
                    "context_update": {},
                    "company_candidates": company_candidates,
                }

            if company is None and is_collection:
                return self._answer_collection(
                    question_id, turn_index, question, metric, year, period, topn
                )

            metric_cn, table_name, field_name, unit = metric
            max_year = self._resolve_max_year(table_name, period)
            # normalize max_year to int if needed
            try:
                if max_year is not None and not isinstance(max_year, int):
                    max_year = int(max_year)
            except Exception:
                # leave as-is
                pass
            # normalize year to integer when possible (guard against string values in context)
            try:
                if year is not None and not isinstance(year, int):
                    year = int(year)
            except Exception:
                # leave as-is if cannot convert
                pass
            if year == -1 and max_year is not None:
                year = max_year - 1
            elif year == -2 and max_year is not None:
                year = max_year
            elif year is None:
                year = max_year

            # final normalization: ensure year is int when possible
            try:
                if year is not None and not isinstance(year, int):
                    year = int(year)
            except Exception:
                pass

            if year is None:
                return {
                    "question_id": question_id,
                    "turn_index": turn_index,
                    "question": question,
                    "status": "need_clarification",
                    "clarification": f"当前{table_name}尚无已入库数据，请先导入核心财务数据后再查询。",
                    "sql": "",
                    "result": [],
                    "analysis": "",
                    "charts": [],
                    "context_update": {},
                }

            # If user didn't specify period, prefer the latest period in the year with non-null metric.
            if (
                company is not None
                and period_from_q is None
                and table_name not in ("__derived__",)
                and isinstance(year, int)
            ):
                period = self._best_period_for_company_metric(
                    company["stock_code"], year, table_name, field_name, period
                )

            if table_name == "__derived__" and field_name == "inventory_turnover_ratio":
                sql = """
                SELECT b.stock_code, b.stock_abbr, b.report_year, b.report_period,
                       CASE WHEN b.asset_inventory IS NULL OR b.asset_inventory=0 THEN NULL
                            ELSE i.operating_expense_cost_of_sales / b.asset_inventory END AS metric_value
                FROM balance_sheet b
                JOIN income_sheet i
                  ON LPAD(i.stock_code,6,'0')=LPAD(b.stock_code,6,'0')
                 AND i.report_year=b.report_year
                 AND i.report_period=b.report_period
                WHERE LPAD(b.stock_code,6,'0')=%s
                  AND b.report_year=%s
                  AND b.report_period=%s
                LIMIT 1
                """
                rows = self.db.fetch_all(
                    sql, (str(company["stock_code"]).zfill(6), year, period)
                )
                used_period = period
                if not rows:
                    for p2 in self._period_fallback_order(period):
                        if p2 == period:
                            continue
                        rows = self.db.fetch_all(
                            sql, (str(company["stock_code"]).zfill(6), year, p2)
                        )
                        if rows:
                            used_period = p2
                            break
                if rows:
                    r = rows[0]
                    analysis = f"{r['stock_abbr']}在{r['report_year']}年{r['report_period']}的存货周转率为{r['metric_value']}次。"
                else:
                    analysis = f"未查到{company['stock_abbr']}在{year}年{used_period}的存货周转率数据。"
                analysis = self._polish_analysis_with_ai(question, analysis, rows)
                return {
                    "question_id": question_id,
                    "turn_index": turn_index,
                    "question": question,
                    "status": "ok",
                    "clarification": "",
                    "sql": " ".join(sql.split()),
                    "result": rows,
                    "analysis": analysis,
                    "charts": [],
                    "context_update": {
                        "metric": metric,
                        "year": year,
                        "period": used_period,
                        "company": company,
                        "is_collection": is_collection,
                    },
                }

            if self._is_yoy_question(question) and table_name != "__derived__":
                sql = f"""
                SELECT t1.stock_code, t1.stock_abbr, t1.report_year, t1.report_period,
                       t1.{field_name} AS current_value,
                       t0.{field_name} AS previous_value,
                       CASE WHEN t0.{field_name}=0 THEN NULL
                            ELSE (t1.{field_name}-t0.{field_name})/t0.{field_name}*100 END AS yoy_growth_rate
                FROM {table_name} t1
                JOIN {table_name} t0
                  ON LPAD(t0.stock_code,6,'0')=LPAD(t1.stock_code,6,'0')
                 AND t0.report_period=t1.report_period
                 AND t0.report_year=t1.report_year-1
                WHERE LPAD(t1.stock_code,6,'0')=%s
                  AND t1.report_year=%s
                  AND t1.report_period=%s
                LIMIT 1
                """
                rows = self.db.fetch_all(
                    sql, (str(company["stock_code"]).zfill(6), year, period)
                )
                used_period = period
                if not rows:
                    for p2 in self._period_fallback_order(period):
                        if p2 == period:
                            continue
                        rows = self.db.fetch_all(
                            sql, (str(company["stock_code"]).zfill(6), year, p2)
                        )
                        if rows:
                            used_period = p2
                            break
                if rows:
                    r = rows[0]
                    analysis = (
                        f"{r['stock_abbr']}在{r['report_year']}年{r['report_period']}的{metric_cn}同比增长率为"
                        f"{r['yoy_growth_rate']}%（同比公式：(当期-上年同期)/上年同期*100）。"
                    )
                else:
                    analysis = f"未查到{company['stock_abbr']}在{year}年{used_period}的{metric_cn}同比数据。"
                analysis = self._polish_analysis_with_ai(question, analysis, rows)
                return {
                    "question_id": question_id,
                    "turn_index": turn_index,
                    "question": question,
                    "status": "ok",
                    "clarification": "",
                    "sql": " ".join(sql.split()),
                    "result": rows,
                    "analysis": analysis,
                    "charts": [],
                    "context_update": {
                        "metric": metric,
                        "year": year,
                        "period": used_period,
                        "company": company,
                        "is_collection": is_collection,
                    },
                }

            if self._is_change_trend_question(question) and table_name != "__derived__":
                sql = f"""
                SELECT t1.stock_code, t1.stock_abbr, t1.report_year, t1.report_period,
                       t1.{field_name} AS metric_value
                FROM {table_name} t1
                WHERE LPAD(t1.stock_code,6,'0')=%s
                  AND t1.report_year IN (%s, %s, %s)
                  AND t1.report_period=%s
                  AND t1.{field_name} IS NOT NULL
                ORDER BY t1.report_year DESC
                LIMIT 5
                """
                years_to_query = (
                    [year, year - 1, year - 2] if year else [2025, 2024, 2023]
                )
                rows = self.db.fetch_all(
                    sql,
                    (
                        str(company["stock_code"]).zfill(6),
                        years_to_query[0],
                        years_to_query[1],
                        years_to_query[2],
                        period,
                    ),
                )
                used_period = period
                if not rows:
                    for p2 in self._period_fallback_order(period):
                        if p2 == period:
                            continue
                        rows = self.db.fetch_all(
                            sql,
                            (
                                str(company["stock_code"]).zfill(6),
                                years_to_query[0],
                                years_to_query[1],
                                years_to_query[2],
                                p2,
                            ),
                        )
                        if rows:
                            used_period = p2
                            break
                if rows and len(rows) >= 2:
                    r_current = rows[0]
                    r_previous = rows[1]
                    # defensive conversions: handle numeric strings with commas or percent signs
                    def _to_num(x):
                        if x is None:
                            return 0.0
                        if isinstance(x, (int, float)):
                            return float(x)
                        s = str(x).strip()
                        # remove thousands separators and percent sign
                        s = s.replace(',', '').replace('%', '')
                        try:
                            return float(s)
                        except Exception:
                            return 0.0
                    current_val = _to_num(r_current.get("metric_value"))
                    previous_val = _to_num(r_previous.get("metric_value"))
                    change_abs = current_val - previous_val
                    change_pct = (
                        (change_abs / previous_val * 100) if previous_val != 0 else None
                    )
                    if change_pct is not None:
                        direction = "增长" if change_pct > 0 else "下降"
                        analysis = (
                            f"{r_current['stock_abbr']}在{r_current['report_year']}年{r_current['report_period']}的{metric_cn}为"
                            f"{current_val:,.2f}{unit}，"
                            f"较{r_previous['report_year']}年同期的{previous_val:,.2f}{unit}，"
                            f"{direction}{abs(change_pct):.2f}%（绝对变化：{change_abs:+,.2f}{unit}）。"
                        )
                    else:
                        analysis = (
                            f"{r_current['stock_abbr']}在{r_current['report_year']}年{r_current['report_period']}的{metric_cn}为"
                            f"{current_val:,.2f}{unit}，"
                            f"较{r_previous['report_year']}年同期的{previous_val:,.2f}{unit}，"
                            f"绝对变化：{change_abs:+,.2f}{unit}。"
                        )
                    if len(rows) >= 3:
                        year_list = [
                            f"{r['report_year']}年{r['report_period']}:{float(r['metric_value'] or 0):,.0f}{unit}"
                            for r in rows[:3]
                        ]
                        analysis += f" 近年数据：{'；'.join(year_list)}。"
                elif rows and len(rows) == 1:
                    r = rows[0]
                    analysis = (
                        f"{r['stock_abbr']}在{r['report_year']}年{r['report_period']}的{metric_cn}为{r['metric_value']}{unit}。"
                        f"（注：缺乏对比期数据，无法计算变化趋势）"
                    )
                else:
                    analysis = f"未查到{company['stock_abbr']}在{year}年{used_period}的{metric_cn}历史数据。"
                analysis = self._polish_analysis_with_ai(question, analysis, rows)
                return {
                    "question_id": question_id,
                    "turn_index": turn_index,
                    "question": question,
                    "status": "ok",
                    "clarification": "",
                    "sql": " ".join(sql.split()),
                    "result": rows,
                    "analysis": analysis,
                    "charts": [],
                    "context_update": {
                        "metric": metric,
                        "year": year,
                        "period": used_period,
                        "company": company,
                        "is_collection": is_collection,
                    },
                }

            if topn:
                sql = f"""
                SELECT stock_code, stock_abbr, {field_name} AS metric_value
                FROM {table_name}
                WHERE report_year=%s AND report_period=%s
                ORDER BY {field_name} DESC
                LIMIT %s
                """
                rows = self.db.fetch_all(sql, (year, period, topn))
                used_period = period
                if not rows:
                    for p2 in self._period_fallback_order(period):
                        if p2 == period:
                            continue
                        rows = self.db.fetch_all(sql, (year, p2, topn))
                        if rows:
                            used_period = p2
                            break
                if not rows:
                    strategy = self._ai_retry_decision(
                        question, year, used_period, False, metric_hint=metric_cn
                    )
                    alt_alias = strategy.get("alternate_metric_alias")
                    alt_metric = (
                        self._metric_from_alias(alt_alias) if alt_alias else None
                    )
                    if alt_metric:
                        alt_cn, alt_table, alt_field, alt_unit = alt_metric
                        sql_alt = f"""
                        SELECT stock_code, stock_abbr, {alt_field} AS metric_value
                        FROM {alt_table}
                        WHERE report_year=%s AND report_period=%s AND {alt_field} IS NOT NULL
                        ORDER BY {alt_field} DESC
                        LIMIT %s
                        """
                        rows_try = self.db.fetch_all(sql_alt, (year, used_period, topn))
                        if rows_try:
                            rows = rows_try
                            sql = sql_alt
                            metric_cn, table_name, field_name, unit = (
                                alt_cn,
                                alt_table,
                                alt_field,
                                alt_unit,
                            )

                chart_path = os.path.join(
                    self.result_dir, f"{question_id}_{turn_index}.jpg"
                )
                if rows:
                    save_bar_chart(
                        rows,
                        "stock_abbr",
                        "metric_value",
                        f"{year}{used_period} {metric_cn} Top{topn}",
                        chart_path,
                    )
                    charts = [chart_path]
                    analysis = self._build_chart_intro(
                        year, used_period, metric_cn, unit, rows, topn
                    )
                else:
                    charts = []
                    analysis = "未查询到符合条件的数据。"
                analysis = self._polish_analysis_with_ai(question, analysis, rows)

                return {
                    "question_id": question_id,
                    "turn_index": turn_index,
                    "question": question,
                    "status": "ok",
                    "clarification": "",
                    "sql": " ".join(sql.split()),
                    "result": rows,
                    "analysis": analysis,
                    "charts": charts,
                    "context_update": {
                        "metric": metric,
                        "year": year,
                        "period": used_period,
                        "company": company,
                        "is_collection": is_collection,
                    },
                }

            sql = f"""
            SELECT stock_code, stock_abbr, report_year, report_period, {field_name} AS metric_value
            FROM {table_name}
            WHERE LPAD(stock_code,6,'0')=%s AND report_year=%s AND report_period=%s
            LIMIT 1
            """
            rows = self.db.fetch_all(
                sql, (str(company["stock_code"]).zfill(6), year, period)
            )
            used_period = period
            if not rows:
                for p2 in self._period_fallback_order(period):
                    if p2 == period:
                        continue
                    rows = self.db.fetch_all(
                        sql, (str(company["stock_code"]).zfill(6), year, p2)
                    )
                    if rows:
                        used_period = p2
                        break
            if not rows:
                strategy = self._ai_retry_decision(
                    question, year, used_period, False, metric_hint=metric_cn
                )
                alt_alias = strategy.get("alternate_metric_alias")
                alt_metric = self._metric_from_alias(alt_alias) if alt_alias else None
                if alt_metric:
                    alt_cn, alt_table, alt_field, alt_unit = alt_metric
                    sql_alt = f"""
                    SELECT stock_code, stock_abbr, report_year, report_period, {alt_field} AS metric_value
                    FROM {alt_table}
                    WHERE LPAD(stock_code,6,'0')=%s AND report_year=%s AND report_period=%s
                    LIMIT 1
                    """
                    rows_try = self.db.fetch_all(
                        sql_alt,
                        (str(company["stock_code"]).zfill(6), year, used_period),
                    )
                    if rows_try:
                        rows = rows_try
                        sql = sql_alt
                        metric_cn, table_name, field_name, unit = (
                            alt_cn,
                            alt_table,
                            alt_field,
                            alt_unit,
                        )

            if rows:
                r = rows[0]
                analysis = f"{r['stock_abbr']}在{r['report_year']}年{r['report_period']}的{metric_cn}为{r['metric_value']}{unit}。"
            else:
                analysis = f"未查到{company['stock_abbr']}在{year}年{used_period}的{metric_cn}数据。"
            analysis = self._polish_analysis_with_ai(question, analysis, rows)

            return {
                "question_id": question_id,
                "turn_index": turn_index,
                "question": question,
                "status": "ok",
                "clarification": "",
                "sql": " ".join(sql.split()),
                "result": rows,
                "analysis": analysis,
                "charts": [],
                "context_update": {
                    "metric": metric,
                    "year": year,
                    "period": used_period,
                    "company": company,
                    "is_collection": is_collection,
                },
            }
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            # print traceback to stdout for debugging
            try:
                print('[TRACEBACK]', tb)
            except Exception:
                pass
            return {
                "question_id": question_id,
                "turn_index": turn_index,
                "question": question,
                "status": "error",
                "clarification": "",
                "sql": "",
                "result": [],
                "analysis": f"执行失败：{e} -- TRACEBACK:\n{tb}",
                "charts": [],
                "context_update": {},
            }
