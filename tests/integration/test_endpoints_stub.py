from fastapi.testclient import TestClient

import app.llm as llm
from app.main import app
from app.pipeline.passes import Extraction

def not_interview(**kw):
    if kw["schema"] is Extraction:
        return {"is_interview": False}
    raise AssertionError("should not score a non-interview")

def test_run_and_test_accept_json_and_return_artifacts(monkeypatch):
    monkeypatch.setattr(llm, "PROVIDERS", [not_interview])
    client = TestClient(app)
    for path in ("/run", "/test"):
        resp = client.post(path, json={"task": {"title": "x"}, "summary": "y"})
        assert resp.status_code == 200
        body = resp.json()
        assert "artifacts" in body and body["artifacts"][0]["type"] == "markdown"

def test_malformed_and_non_dict_bodies_never_500(monkeypatch):
    monkeypatch.setattr(llm, "PROVIDERS", [not_interview])
    client = TestClient(app)
    for body in (b"not json", b"", b"[1,2,3]"):
        resp = client.post("/run", content=body, headers={"content-type": "application/json"})
        assert resp.status_code == 200
        assert "artifacts" in resp.json()
