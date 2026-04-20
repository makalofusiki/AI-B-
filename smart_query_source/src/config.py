import json
import os
from pathlib import Path


# Prefer local SQLite db: first look next to executable (for bundled exe), then project data/, otherwise use MySQL settings.
DATA_DIR = Path(__file__).resolve().parents[1] / 'data'

# candidate DB filenames
_sqlite_names = ['financial_reports.sqlite', 'finance_data.sqlite', 'finance.sqlite']

# check bundled exe directory when frozen (PyInstaller)
_sqlite_path = None
try:
    import sys
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
        for n in _sqlite_names:
            p = exe_dir / n
            if p.exists():
                _sqlite_path = str(p)
                break
        # also check exe_dir/data/
        if not _sqlite_path:
            for n in _sqlite_names:
                p = exe_dir / 'data' / n
                if p.exists():
                    _sqlite_path = str(p)
                    break
except Exception:
    _sqlite_path = None

# fallback to project data directory
if not _sqlite_path:
    for n in _sqlite_names:
        p = DATA_DIR / n
        if p.exists():
            _sqlite_path = str(p)
            break

if _sqlite_path:
    DB_CONFIG = {"sqlite_path": _sqlite_path}
else:
    DB_CONFIG = {
        "host": "127.0.0.1",
        "port": 3306,
        "user": "root",
        "password": "123456",
        "database": "finance_data",
        "charset": "utf8mb4",
    }

RESULT_DIR = r"D:\BaiduNetdiskDownload\data\smart_query_assistant\result"

LLM_CONFIG = {
    "provider": os.getenv("LLM_PROVIDER", "moonshot"),
    "base_url": os.getenv("LLM_BASE_URL", "https://api.moonshot.cn/v1"),
    "api_key": os.getenv("LLM_API_KEY", ""),
    "model": os.getenv("LLM_MODEL", "kimi2.5"),
    "timeout_sec": int(os.getenv("LLM_TIMEOUT_SEC", "20")),
}


def _load_local_llm_config() -> dict:
    local_path = Path(__file__).resolve().parents[1] / "config.local.json"
    if not local_path.exists():
        return {}
    with local_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


_local_llm_config = _load_local_llm_config()
for _key in ("provider", "base_url", "api_key", "model", "timeout_sec"):
    if _key in _local_llm_config and _local_llm_config[_key] not in (None, ""):
        LLM_CONFIG[_key] = _local_llm_config[_key]
if LLM_CONFIG.get("timeout_sec") is not None:
    LLM_CONFIG["timeout_sec"] = int(LLM_CONFIG["timeout_sec"])

# Service-level API key for protecting backend endpoints. Prefer environment variable SERVICE_API_KEY or
# set "service_api_key" in config.local.json (project root). If empty, auth is disabled (development only).
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "")
if "service_api_key" in _local_llm_config and _local_llm_config.get("service_api_key"):
    SERVICE_API_KEY = _local_llm_config.get("service_api_key")
