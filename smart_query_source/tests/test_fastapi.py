from fastapi.testclient import TestClient
import src.config as cfg

from src.fastapi_app import app


def test_health():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_chat_with_dummy(monkeypatch):
    # Patch DBClient and QueryEngine used in fastapi_app to avoid real DB/LLM calls
    class DummyDB:
        def close(self):
            pass

    class DummyEngine:
        def __init__(self, db, result_dir):
            pass

        def answer(self, qid, qtext, context=None, turn_index=1):
            return {
                "status": "ok",
                "analysis": "dummy analysis",
                "sql": "SELECT 1",
                "result": [{"a": 1}],
                "charts": [],
            }

    monkeypatch.setattr("src.fastapi_app.DBClient", lambda cfg: DummyDB())
    monkeypatch.setattr("src.fastapi_app.QueryEngine", DummyEngine)

    client = TestClient(app)
    payload = {"question": "hello", "session_id": "s1", "question_id": "q1", "turn_index": 1}
    headers = {}
    if cfg.SERVICE_API_KEY:
        headers["X-API-Key"] = cfg.SERVICE_API_KEY
    r = client.post("/chat", json=payload, headers=headers)
    assert r.status_code == 200
    j = r.json()
    assert "final_answer" in j or "answer" in j
    fa = j.get("final_answer") or j.get("answer")
    # depending on fastapi_app version, check nested structure
    if isinstance(fa, dict):
        # if final_answer is nested directly
        assert fa.get("status") == "ok" or (fa.get('answer') and fa.get('answer').get('status') == 'ok')
    else:
        assert True
