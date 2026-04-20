from __future__ import annotations

import json
import urllib.request
from typing import Any, Dict, Optional


class LLMClient:
    def __init__(self, cfg: Dict[str, Any]):
        self.base_url = (cfg.get("base_url") or "").rstrip("/")
        self.api_key = cfg.get("api_key") or ""
        self.model = cfg.get("model") or "gpt-4o-mini"
        self.timeout_sec = int(cfg.get("timeout_sec") or 20)

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def _post_chat(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)

    def _chat_json(self, system: str, user: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            data = self._post_chat(payload)
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                return None
            parsed = json.loads(content)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    def parse_slots(self, question: str) -> Optional[Dict[str, Any]]:
        """Parse slots using cloud LLM when enabled; otherwise use a lightweight local heuristic so the app works offline."""
        if self.enabled:
            system = (
                "你是金融问数系统的槽位抽取器。"
                "只输出JSON，不要输出任何额外文字。"
                "JSON字段: metric_alias, company_name, stock_code, year, period, topn, is_collection。"
                "period 仅允许: Q1, HY, Q3, FY。"
                "无法判断时字段置空。"
            )
            user = f"问题：{question}"
            return self._chat_json(system, user)

        # Local heuristic fallback
        out = {
            "metric_alias": None,
            "company_name": None,
            "stock_code": None,
            "year": None,
            "period": None,
            "topn": None,
            "is_collection": False,
        }
        if not question:
            return out
        # year
        import re

        m = re.search(r"(20\d{2})年", question)
        if m:
            try:
                out["year"] = int(m.group(1))
            except Exception:
                pass
        if "前三季度" in question:
            out["period"] = "Q3"
        for k, v in [("Q1", "Q1"), ("HY", "HY"), ("Q3", "Q3"), ("FY", "FY")]:
            if k in question:
                out["period"] = v
                break
        # topn
        m2 = re.search(r"(?:top|TOP|前)\s*(\d+)", question)
        if m2:
            try:
                out["topn"] = int(m2.group(1))
            except Exception:
                pass
        # stock code
        m3 = re.search(r"(?<!\d)(\d{3,6})(?!\d)", question)
        if m3:
            out["stock_code"] = m3.group(1)
        # company name heuristic: look for Chinese 2+ chars + common suffix
        m4 = re.search(r"([\u4e00-\u9fa5]{2,}?(股份|药业|制药|集团|医药))", question)
        if m4:
            out["company_name"] = m4.group(1)
        # metric alias: pick a known keyword (simple)
        for kw in ["净利润", "利润总额", "净资产收益率", "收益率", "营业收入", "收入"]:
            if kw in question:
                out["metric_alias"] = kw
                break
        if any(k in question for k in ["哪些", "排名", "前", "多少家", "统计"]):
            out["is_collection"] = True
        return out

    def suggest_retry_strategy(
        self,
        question: str,
        year: Optional[int],
        period: str,
        has_threshold: bool,
        metric_hint: str = "",
    ) -> Optional[Dict[str, Any]]:
        if self.enabled:
            system = (
                "你是金融查询重试策略器。"
                "只输出JSON。字段: retry(bool), fallback_period(Q3/HY/FY/''), drop_threshold(bool), topn(int或null), alternate_metric_alias(string或空)。"
                "仅在原查询为空时给出可执行重试建议，优先同义指标替代和期间降级。"
            )
            user = (
                f"问题:{question}\n"
                f"当前条件: year={year}, period={period}, has_threshold={has_threshold}, metric_hint={metric_hint}\n"
                "请返回最小化放宽策略；alternate_metric_alias 必须是问题里的财务指标近义词。"
            )
            return self._chat_json(system, user)

        # Local fallback: conservative suggestions
        out = {}
        if period and period != "FY":
            out["fallback_period"] = "FY"
        if has_threshold:
            out["drop_threshold"] = True
        return out

    def generate_answer(
        self, question: str, default_analysis: str, rows: Any
    ) -> Optional[str]:
        if self.enabled:
            system = (
                "你是金融数据问答助手。根据查询结果生成简洁结论。"
                "禁止捏造数据；如果结果为空，明确说未查到。"
                "重要规则："
                "1. 如果查询到部分公司数据，即使不是全部公司，也要基于已有数据给出结论（如'部分公司有数据：A公司XX、B公司XX'），不要说'无法对比'或'无法完整对比'。"
                "2. 如果对比问题只查到部分数据，应列出有数据的公司并给出对比结论。"
                "3. 变化趋势问题必须明确说明变化方向（增长/下降/持平），不能只给数值。"
                "4. 对比问题必须明确说明哪个更高/更低、排名如何。"
                "仅输出一段中文文本。"
            )
            preview = rows[:5] if isinstance(rows, list) else rows
            payload = {
                "model": self.model,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": f"问题:{question}\n默认结论:{default_analysis}\n结果样例:{json.dumps(preview, ensure_ascii=False, default=str)}",
                    },
                ],
            }
            try:
                data = self._post_chat(payload)
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                c = (content or "").strip()
                return c if c else None
            except Exception:
                return None

        # Local fallback: simple templated analysis
        if not rows:
            return default_analysis or "未查询到符合条件的数据。"
        try:
            if isinstance(rows, list):
                # list of dicts
                non_null = [r for r in rows if r and any(v not in (None, '') for v in r.values())]
                if not non_null:
                    return "查询返回空值数据。"
                top = non_null[0]
                abbr = top.get('stock_abbr') or top.get('stock_name') or top.get('company') or ''
                val = top.get('metric_value') if isinstance(top.get('metric_value'), (int, float)) else str(top.get('metric_value'))
                return f"结果样例：{abbr} 的指标值为 {val}。基于现有数据：{default_analysis or ''}" if abbr else (default_analysis or '')
        except Exception:
            return default_analysis or None
        return default_analysis or None
