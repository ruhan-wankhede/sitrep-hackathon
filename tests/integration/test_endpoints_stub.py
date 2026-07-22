from fastapi.testclient import TestClient
from app.main import app

def test_run_and_test_accept_json_and_return_artifacts():
    client = TestClient(app)
    for path in ("/run", "/test"):
        resp = client.post(path, json={"task": {"title": "x"}, "summary": "y"})
        assert resp.status_code == 200
        body = resp.json()
        assert "artifacts" in body and body["artifacts"][0]["type"] == "markdown"
