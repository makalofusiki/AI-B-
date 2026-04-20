# 参赛作品说明（后端与数据库）

本项目是一个面向**中药上市公司财务问答**的参赛作品，核心能力是把自然语言问题转为结构化数据库查询，并返回结论、明细结果和可视化图表。

## 1. 项目定位与整体结构

- 后端主目录：`smart_query_source/src`
- 前端主目录：`smart_query_source/frontend`
- 批处理与测试：`smart_query_source/scripts`、`smart_query_source/tests`

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
=======
# 智能问数助手 (Smart Query Assistant)

面向上市公司财务数据的离线优先桌面查询与可视化应用。

核心亮点
- 支持自然语言到 SQL 的查询（公司 + 指标 + 期间）
- 离线优先：捆绑 SQLite，放在可执行文件同级即可被自动识别
- 可选 AI 增强：支持接入 Kimi/DeepSeek 做意图补全
- 打包友好：推荐 PyInstaller --onedir 发行

快速开始（推荐）
1. 使用已打包的桌面应用（便携 onedir）
   - 可执行文件路径示例：
     D:\BaiduNetdiskDownload\data\smart_query_assistant\dist\smart_query_desktop_onedir\smart_query_desktop_onedir.exe
   - 若要替换离线数据，请把你的 SQLite 文件命名为 `finance_data.sqlite` 并放到 exe 同级的 `data\` 或直接放在 exe 目录下；应用启动时会优先使用该文件。

2. 将 Excel 导入到离线 SQLite（如需把附件数据打包进去）
   - 脚本： `scripts\import_excel_to_sqlite.py`
   - 示例：
     ```powershell
     python .\scripts\import_excel_to_sqlite.py -i "D:\全部数据\正式数据\附件1：中药上市公司基本信息（截至到2025年12月22日）.xlsx" -o src\data\finance_data.sqlite
     ```
   - 导入后可替换 `dist\...\_internal\data\finance_data.sqlite` 以更新已打包数据库（或在打包前将 `src/data/finance_data.sqlite` 替换）

开发模式运行
1. 安装依赖： `pip install -r requirements.txt`
2. 启动后端： `python src/backend_api.py --host 127.0.0.1 --port 8010`
3. 启动前端（若需要）: `cd frontend && npm install && npm run dev`

打包说明（建议）
- 推荐使用 `pyinstaller --onedir`，确保把 `src/data`（或已生成的 SQLite）和 PySide6 插件目录通过 `--add-data` 一并加入。
- 注意：Qt SQL 驱动的第三方客户端 DLL（如 fbclient.dll / OCI.dll / LIBPQ.dll）通常不需要，除非你打算连接这些数据库。

重要文件与路径
- 可执行（示例）：
  `dist\smart_query_desktop_onedir\smart_query_desktop_onedir.exe`
- 捆绑离线 DB：
  `dist\smart_query_desktop_onedir\_internal\data\finance_data.sqlite`
- 导入脚本： `scripts\import_excel_to_sqlite.py`
- 验证脚本： `scripts\check_sqlite_tables.py`
- 验收脚本： `dist\run_acceptance.ps1`（自动截图、收集日志）

常见操作
- 替换捆绑 DB：把新的 `finance_data.sqlite` 复制到 exe 同级或 `_internal\data\`，然后重启应用。
- 在打包前替换：把 `src/data/finance_data.sqlite` 替换为已导入数据，然后重新运行 PyInstaller

致谢与联系方式
- 本项目为内部使用，文档与发行请遵循内部发布流程。