from fastapi.testclient import TestClient
from app.main import app

def test_run_and_test_accept_json_and_return_artifacts():
    client = TestClient(app)
    for path in ("/run", "/test"):
        resp = client.post(path, json={"task": {"title": "x"}, "summary": "y"})
        assert resp.status_code == 200
        body = resp.json()
        assert "artifacts" in body and body["artifacts"][0]["type"] == "markdown"

def test_malformed_and_non_dict_bodies_never_500():
    client = TestClient(app)
    for body in (b"not json", b"", b"[1,2,3]"):
        resp = client.post("/run", content=body, headers={"content-type": "application/json"})
        assert resp.status_code == 200
        assert "artifacts" in resp.json()
