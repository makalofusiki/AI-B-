from fastapi import FastAPI, Depends, HTTPException, Header, Request, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any
import os
import logging
from logging.handlers import RotatingFileHandler
import traceback
from fastapi.responses import JSONResponse
from datetime import datetime
import mimetypes
import uuid
import threading

from config import DB_CONFIG, RESULT_DIR, SERVICE_API_KEY
from db_client import DBClient
from query_engine import QueryEngine
from session_store import SessionStore
from batch_runner import run_batch

app = FastAPI(title="SmartQuery Assistant API")

# Configure structured logging to logs/backend.log
_log_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "logs"))
os.makedirs(_log_dir, exist_ok=True)
_log_file = os.path.join(_log_dir, "backend.log")
_handler = RotatingFileHandler(_log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
_formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
_handler.setFormatter(_formatter)
logger = logging.getLogger("smart_query_assistant")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(_handler)

# Enable CORS so the frontend dev server or other origins can call the API directly.
# Configure FRONTEND_ORIGINS env var as comma-separated list to limit allowed origins.
from fastapi.middleware.cors import CORSMiddleware
_frontend_origins = os.getenv('FRONTEND_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174')
_allowed_origins = [o.strip() for o in _frontend_origins.split(',') if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins or ['*'],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# debug exception handler (enable by setting DEBUG_API=1 in env)
DEBUG_API = os.getenv('DEBUG_API','0') == '1'

@app.exception_handler(Exception)
async def all_exception_handler(request, exc):
    logger.exception("Unhandled exception", exc_info=exc)
    if DEBUG_API:
        return JSONResponse(status_code=500, content={"error": str(exc), "trace": traceback.format_exc()})
    return JSONResponse(status_code=500, content={"error": "Internal Server Error"})

SESSION_DB= os.path.abspath(r"D:\BaiduNetdiskDownload\data\smart_query_assistant\logs\session_store.sqlite")
session_store = SessionStore(SESSION_DB)

# Simple in-memory job store for background batch runs
JOBS: Dict[str, dict] = {}


def verify_api_key(x_api_key: Optional[str] = Header(None)):
    # If SERVICE_API_KEY is empty, auth disabled (development).
    if SERVICE_API_KEY:
        if not x_api_key or x_api_key != SERVICE_API_KEY:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return True


class ChatRequest(BaseModel):
    session_id: Optional[str] = "default"
    question_id: Optional[str] = "CHAT"
    turn_index: Optional[int] = 1
    question: str


class BatchRequest(BaseModel):
    input_files: Optional[list] = None
    output_xlsx: Optional[str] = None
    result_dir: Optional[str] = None


class SessionClearRequest(BaseModel):
    session_id: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(req: ChatRequest, _=Depends(verify_api_key)):
    db = DBClient(DB_CONFIG)
    try:
        engine = QueryEngine(db, RESULT_DIR)
        context = session_store.get_context(req.session_id) or {}
        try:
            answer = engine.answer(req.question_id, req.question, context=context, turn_index=req.turn_index)
        except Exception as e:
            # Log and return a structured JSON so frontend can handle gracefully
            logger.exception("Unhandled exception while answering question")
            return {
                "session_id": req.session_id,
                "question_id": req.question_id,
                "answer": {"text": "", "error": str(e)}
            }
        if answer.get("context_update"):
            context.update(answer["context_update"])
            session_store.save_context(req.session_id, context)
        return {"session_id": req.session_id, "question_id": req.question_id, "answer": answer}
    finally:
        db.close()


@app.post("/session/clear")
def session_clear(req: SessionClearRequest, _=Depends(verify_api_key)):
    session_store.clear(req.session_id)
    return {"status": "cleared", "session_id": req.session_id}


@app.post("/batch")
def batch(req: BatchRequest, background_tasks: BackgroundTasks, _=Depends(verify_api_key)):
    """Start a background batch job. Returns a job_id which can be checked via /batch/status/{job_id}.
    For compatibility, this endpoint schedules the run in the background instead of blocking the request.
    """
    input_files = req.input_files or [r"D:\\BaiduNetdiskDownload\\data\\附件4：问题汇总.xlsx", r"D:\\BaiduNetdiskDownload\\data\\附件6：问题汇总.xlsx"]
    output_xlsx = req.output_xlsx or r"D:\\BaiduNetdiskDownload\\data\\smart_query_assistant\\result\\result_2.xlsx"
    result_dir = req.result_dir or RESULT_DIR
    os.makedirs(result_dir, exist_ok=True)

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "status": "queued",
        "created": datetime.now().isoformat(),
        "input_files": input_files,
        "output_xlsx": output_xlsx,
        "result_dir": result_dir,
    }

    def _run_batch_job(job_id, input_files, output_xlsx, result_dir):
        logger.info(f"Job {job_id}: started")
        JOBS[job_id]["status"] = "running"
        JOBS[job_id]["started"] = datetime.now().isoformat()
        try:
            run_batch(input_files=input_files, output_xlsx=output_xlsx, result_dir=result_dir)
            JOBS[job_id]["status"] = "completed"
            JOBS[job_id]["finished"] = datetime.now().isoformat()
            JOBS[job_id]["output_xlsx"] = output_xlsx
            logger.info(f"Job {job_id}: completed")
        except Exception as e:
            logger.exception(f"Job {job_id}: failed")
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["error"] = str(e)
            JOBS[job_id]["finished"] = datetime.now().isoformat()

    # Run job in a separate daemon thread so the server process isn't blocked by long synchronous work
    t = threading.Thread(target=_run_batch_job, args=(job_id, input_files, output_xlsx, result_dir), daemon=True)
    t.start()

    return {"status": "queued", "job_id": job_id}


@app.get("/batch/status/{job_id}")
def batch_status(job_id: str, _=Depends(verify_api_key)):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# Serve result files and provide a listing for the frontend
try:
    from fastapi.staticfiles import StaticFiles
    # mount static files under /results/files
    if os.path.isdir(RESULT_DIR):
        app.mount("/results/files", StaticFiles(directory=RESULT_DIR), name="results_files")
except Exception:
    logger.exception("Failed to mount result static files")

# Mount frontend production build if present (serve SPA)
try:
    from fastapi.staticfiles import StaticFiles as _StaticFiles
    _frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist'))
    if os.path.isdir(_frontend_dist):
        try:
            app.mount('/', _StaticFiles(directory=_frontend_dist, html=True), name='frontend')
            logger.info(f"Mounted frontend dist at {_frontend_dist}")
        except Exception:
            logger.exception("Failed to mount frontend dist")
except Exception:
    logger.exception("Failed to import StaticFiles for frontend mount")


@app.get("/results/list")
def results_list(_=Depends(verify_api_key)):
    """Return a JSON list of result files in RESULT_DIR with URLs and metadata."""
    try:
        files = []
        if not os.path.isdir(RESULT_DIR):
            return {"files": files}
        for fname in sorted(os.listdir(RESULT_DIR)):
            fpath = os.path.join(RESULT_DIR, fname)
            if os.path.isfile(fpath):
                try:
                    size = os.path.getsize(fpath)
                    mtime = datetime.fromtimestamp(os.path.getmtime(fpath)).isoformat()
                except Exception:
                    size = None
                    mtime = None
                ctype = mimetypes.guess_type(fname)[0] or 'application/octet-stream'
                files.append({
                    "name": fname,
                    "url": f"/results/files/{fname}",
                    "size": size,
                    "mtime": mtime,
                    "content_type": ctype
                })
        return {"files": files}
    except Exception as e:
        logger.exception("Error listing result files")
        raise HTTPException(status_code=500, detail="Failed to list results")
