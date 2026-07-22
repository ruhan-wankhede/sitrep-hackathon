import app.llm as llm
from app.analytics import (
    contradiction_candidates, confirm_contradiction, coverage, disagreements,
)

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
