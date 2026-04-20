# AI-B- 参赛作品说明（后端与数据库）

本项目是一个面向**中药上市公司财务问答**的参赛作品，核心能力是把自然语言问题转为结构化数据库查询，并返回结论、明细结果和可视化图表。

## 1. 项目定位与整体结构

- 后端主目录：`/home/runner/work/AI-B-/AI-B-/smart_query_source/src`
- 前端主目录：`/home/runner/work/AI-B-/AI-B-/smart_query_source/frontend`
- 批处理与测试：`/home/runner/work/AI-B-/AI-B-/smart_query_source/scripts`、`/home/runner/work/AI-B-/AI-B-/smart_query_source/tests`

核心运行链路：
1. 前端调用 `/chat`（`fastapi_app.py`）。
2. 后端创建 `QueryEngine`，完成“指标/公司/年份/期间/TopN”槽位解析。
3. 通过 `DBClient` 执行 SQL（先做 EXPLAIN 校验）。
4. 返回 `analysis + result + sql + charts`，并把上下文写入会话库。

---

## 2. 后端主要程序逻辑

### 2.1 API 层（`fastapi_app.py`）

提供的关键接口：
- `GET /health`：健康检查。
- `POST /chat`：单轮/多轮问答主入口。
- `POST /session/clear`：清除会话上下文。
- `POST /batch` + `GET /batch/status/{job_id}`：批量任务异步执行与状态查询。
- `GET /results/list`：返回结果目录文件清单。

关键特性：
- 支持 `X-API-Key`（`SERVICE_API_KEY`）鉴权。
- CORS 配置支持前端直连。
- 后台批任务使用线程异步执行。
- 结果文件可通过静态路由访问。

### 2.2 查询引擎（`query_engine.py`）

`QueryEngine.answer()` 是后端核心：
1. **文本解析**：提取指标、公司、年份、期间、TopN、阈值、同比/趋势/对比意图。
2. **别名与歧义消解**：  
   - 公司别名来自 `listed_company_basic_info + company_alias`。  
   - 指标别名来自 `metric_mapping.py + metric_alias`。
3. **上下文续聊**：若当前问题信息不全，会复用会话 context。
4. **智能回退策略**：数据缺失时可切换期间、放宽阈值、替代指标。
5. **SQL 生成与执行**：区分单公司查询、集合统计、同比、趋势、TopN 等场景。
6. **结果增强**：可生成柱状图（`charting.py`），并可选用 LLM 润色结论文本。

### 2.3 数据访问层（`db_client.py`）

- 同时支持 **MySQL** 和 **SQLite**。
- 若检测到本地 SQLite 文件（`financial_reports.sqlite` / `finance_data.sqlite`），优先离线运行。
- 执行前统一做 EXPLAIN 校验，降低非法 SQL 风险。
- 兼容处理 MySQL/SQLite 占位符与函数差异（如 `LPAD/CONCAT/FIELD`）。

### 2.4 会话与批处理

- `session_store.py`：会话上下文持久化到 SQLite 表 `chat_sessions`，支持 TTL 过期清理。
- `batch_runner.py`：批量读取问题 Excel，逐题执行问答并产出结果；失败记录写入 `failed_jobs.sqlite` 的 `failed_jobs` 表。

---

## 3. 数据库详细内容

### 3.1 核心业务表（财务主干）

以下 4 张表是财务查询主干，按 `stock_code + report_year + report_period` 对齐：
- `income_sheet`（利润表相关）
- `balance_sheet`（资产负债表相关）
- `cash_flow_sheet`（现金流量表相关）
- `core_performance_indicators_sheet`（核心业绩指标）

常用字段示例：
- 维度字段：`stock_code`, `stock_abbr`, `report_year`, `report_period`
- 指标字段：`net_profit`, `total_operating_revenue`, `asset_total_assets`, `liability_total_liabilities`, `operating_cf_net_amount`, `eps`, `roe` 等

### 3.2 公司与指标映射表

- `listed_company_basic_info`：公司主数据（证券代码、简称、全称等）。
- `company_alias`：公司简称/别名映射，用于口语化输入匹配。
- `metric_alias`：指标别名映射，支持“营收/销售额/扣非ROE”等自然语言同义词。
- `report_export_ratio`：出口业务占比等扩展指标表。

### 3.3 研报抽取增强表

由研报抽取脚本构建，用于从原始文本补全结构化财务字段：
- `sse_report_index` / `szse_report_index`：报告索引（文件、公司、年份、期间等）。
- `sse_financial_facts` / `szse_financial_facts`：从文本抽取的指标事实值。
- 原始页表：`sh_reports_raw_pages`（脚本中作为抽取源）。

相关脚本包括：
- `bootstrap_core_from_reports.py`：从研报初始化四大核心财务表。
- `upgrade_sse_database.py`：建立索引/事实表并回填核心表。
- `backfill_income_expenses_from_reports.py`：回填利润表费用字段。
- `backfill_company_coverage.py`：补齐公司-年份-期间覆盖。

### 3.4 运行时 SQLite 表

- `chat_sessions`：会话上下文（来自 `session_store.py`）。
- `failed_jobs`：批处理失败任务明细（来自 `batch_runner.py`）。

---

## 4. 数据流与离线部署

1. MySQL 作为原始/开发数据主库。  
2. 通过 `mysql_to_sqlite.py` 导出为离线 SQLite（`smart_query_source/data/financial_reports.sqlite`）。  
3. 部署或打包时优先加载 SQLite，实现离线查询。  
4. 查询过程中的图表、批处理 JSON/Excel 输出到结果目录（`RESULT_DIR`）。

---

## 5. 参赛作品价值点（后端与数据库视角）

- **可解释**：返回 SQL、结构化结果和文本结论，便于核验。
- **离线可用**：SQLite 优先策略适合赛场演示与无网环境。
- **可扩展**：指标别名、公司别名、研报事实表可持续增量。
- **工程化**：支持 API、批处理、会话上下文、失败追踪与结果文件管理。
