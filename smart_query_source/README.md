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

