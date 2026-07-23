import app.llm as llm
from app.analytics import (
    composite, contradiction_candidates, confirm_contradiction, coverage,
    disagreements, recommendation,
)

def test_composite_averages_competency_scores():
    assert composite([4.0, 4.0, 3.0, None]) == 3.7
    assert composite([None, None]) is None

def test_recommendation_bands_by_composite():
    assert recommendation(3.6, 5, [])["label"] == "Strong hire"
    assert recommendation(3.0, 5, [])["label"] == "Hire"
    assert recommendation(2.2, 5, [])["label"] == "Lean no"
    assert recommendation(1.4, 5, [])["label"] == "No hire"

def test_recommendation_blocker_caps_verdict_regardless_of_score():
    r = recommendation(3.9, 5, ["unresolved claim contradiction"])
    assert r["label"] == "Needs follow-up"
    assert "unresolved claim contradiction" in r["reason"]

def test_recommendation_insufficient_data_when_no_composite():
    assert recommendation(None, 0, [])["label"] == "Insufficient data"

def test_coverage_splits_assessed_and_unassessed():
    rows = [
        {"competency": "A", "score": 3, "interviewer": "P"},
        {"competency": "B", "score": None, "interviewer": "P"},
        {"competency": "B", "score": 2, "interviewer": "M"},
        {"competency": "C", "score": None, "interviewer": "M"},
    ]
    cov = coverage(rows)
    assert cov["assessed"] == ["A", "B"]
    assert cov["unassessed"] == ["C"]

def test_disagreement_requires_spread_of_two():
    rows = [
        {"competency": "A", "score": 4, "interviewer": "P"},
        {"competency": "A", "score": 2, "interviewer": "M"},
        {"competency": "B", "score": 3, "interviewer": "P"},
        {"competency": "B", "score": 2, "interviewer": "M"},
    ]
    d = disagreements(rows)
    assert len(d) == 1 and d[0]["competency"] == "A" and d[0]["spread"] == 2

def test_contradiction_candidates_same_category_conflicting_values():
    claims = [
        {"category": "team_size", "statement": "led 8", "value": "8", "interview_id": 1},
        {"category": "team_size", "statement": "team of 3", "value": "3", "interview_id": 3},
        {"category": "tenure", "statement": "8 years", "value": "8", "interview_id": 1},
    ]
    pairs = contradiction_candidates(claims)
    assert len(pairs) == 1
    assert {pairs[0][0]["value"], pairs[0][1]["value"]} == {"8", "3"}

def test_confirm_contradiction_uses_llm_verdict(monkeypatch):
    monkeypatch.setattr(llm, "PROVIDERS", [lambda **kw: {"contradictory": True}])
    assert confirm_contradiction({"statement": "led 8"}, {"statement": "team of 3"}) is True
