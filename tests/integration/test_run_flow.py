from fastapi.testclient import TestClient

import app.llm as llm
from app.main import app
from app.pipeline.passes import Extraction

PAYLOAD = {"task": {"title": "Interview debrief", "description": ""},
           "summary": "Priya interviewed Aisha Verma for Backend Engineer. Aisha said she led a team of 8. "
                      "She explained a sharding migration in depth.",
           "attendees": ["Priya", "Aisha Verma"]}

def fake_llm(**kw):
    if kw["schema"] is Extraction:
        return {"is_interview": True, "candidate_name": "Aisha Verma", "role_title": "Backend Engineer",
                "interviewer": "Priya",
                "exchanges": [{"question": "sharding?", "answer_summary": "explained migration in depth"}],
                "claims": [{"category": "team_size", "statement": "led a team of 8", "value": "8"}]}
    name = kw["schema"].__name__
    if name == "ScoreSet":
        return {"scores": [{"competency": "Technical depth", "score": 4,
                            "evidence": ["explained a sharding migration in depth"], "rationale": "strong"}]}
    if name == "FlagSet":
        return {"flags": []}
    return {"contradictory": False}

def test_run_produces_scorecard_artifact(client_with_db, monkeypatch):
    monkeypatch.setattr(llm, "PROVIDERS", [fake_llm])
    resp = client_with_db.post("/run", json=PAYLOAD)
    assert resp.status_code == 200
    content = resp.json()["artifacts"][0]["content"]
    assert "Technical depth" in content and "Exceptional" in content

def test_non_interview_gets_polite_artifact(client_with_db, monkeypatch):
    def not_interview(**kw):
        if kw["schema"] is Extraction:
            return {"is_interview": False}
        raise AssertionError("should not score a non-interview")
    monkeypatch.setattr(llm, "PROVIDERS", [not_interview])
    resp = client_with_db.post("/run", json={"task": {"title": "Sprint sync"}, "summary": "We planned the sprint."})
    assert resp.status_code == 200
    assert "doesn't look like an interview" in resp.json()["artifacts"][0]["content"]

def test_llm_down_returns_graceful_artifact_not_500(client_with_db, monkeypatch):
    def boom(**kw):
        raise RuntimeError("both providers down")
    monkeypatch.setattr(llm, "PROVIDERS", [boom])
    monkeypatch.setattr(llm, "RETRY_SLEEP", 0)
    resp = client_with_db.post("/run", json=PAYLOAD)
    assert resp.status_code == 200
    assert "couldn't analyze" in resp.json()["artifacts"][0]["content"]

def fake_llm_out_of_range_score(**kw):
    if kw["schema"] is Extraction:
        return {"is_interview": True, "candidate_name": "Aisha Verma", "role_title": "Backend Engineer",
                "interviewer": "Priya",
                "exchanges": [{"question": "sharding?", "answer_summary": "explained migration in depth"}],
                "claims": [{"category": "team_size", "statement": "led a team of 8", "value": "8"}]}
    name = kw["schema"].__name__
    if name == "ScoreSet":
        return {"scores": [{"competency": "Technical depth", "score": 5,
                            "evidence": ["explained a sharding migration in depth"], "rationale": "strong"}]}
    if name == "FlagSet":
        return {"flags": []}
    return {"contradictory": False}

def test_out_of_range_score_returns_200_with_artifacts(client_with_db, monkeypatch):
    monkeypatch.setattr(llm, "PROVIDERS", [fake_llm_out_of_range_score])
    monkeypatch.setattr(llm, "RETRY_SLEEP", 0)
    resp = client_with_db.post("/run", json=PAYLOAD)
    assert resp.status_code == 200
    assert "artifacts" in resp.json()
