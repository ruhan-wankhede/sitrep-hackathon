import app.llm as llm
from app.models import ProbeRow
from app.pipeline.passes import CompetencyScore, Extraction, FlagSet, ScoreSet
from app.pipeline.persist import save_interview
from app.pipeline.probes import refresh_brief

RUBRIC = ["Technical depth", "System design"]

def _seed_weak(session):
    ext = Extraction(is_interview=True, candidate_name="Aisha Verma", role_title="Backend Engineer",
                     interviewer="Priya", exchanges=[], claims=[])
    ss = ScoreSet(scores=[CompetencyScore(competency="Technical depth", score=2,
                                          evidence=["was vague on throughput"], rationale="thin")])
    return save_interview(session, ext, ss, FlagSet(), "s1", {}, "test", RUBRIC)

def test_refresh_brief_writes_probes_and_returns_feedback(session, monkeypatch):
    iv = _seed_weak(session)
    monkeypatch.setattr(llm, "PROVIDERS", [lambda **kw: {
        "probes": [
            {"competency": "System design", "question": "Design a rate limiter.", "reason": "unprobed"},
            {"competency": "Technical depth", "question": "Who owned the migration call?", "reason": "vague"},
        ],
        "feedback_email": "Thanks for making the time — your debugging instincts stood out.",
    }])
    feedback = refresh_brief(session, iv.candidate_id, "Backend Engineer", "Aisha Verma", ["System design"])
    rows = session.query(ProbeRow).filter(ProbeRow.candidate_id == iv.candidate_id).all()
    assert {r.competency for r in rows} == {"System design", "Technical depth"}
    assert "debugging instincts" in feedback

def test_refresh_brief_skips_when_nothing_assessed(session, monkeypatch):
    # A candidate with no scored interviews yet: no LLM call, no probes, empty feedback.
    ext = Extraction(is_interview=True, candidate_name="New Person", role_title="Backend Engineer",
                     interviewer="Sam", exchanges=[], claims=[])
    ss = ScoreSet(scores=[CompetencyScore(competency="Technical depth", score=None, evidence=[], rationale="")])
    iv = save_interview(session, ext, ss, FlagSet(), "s2", {}, "test", RUBRIC)
    called = {"n": 0}
    def fake(**kw):
        called["n"] += 1
        return {"probes": [], "feedback_email": ""}
    monkeypatch.setattr(llm, "PROVIDERS", [fake])
    feedback = refresh_brief(session, iv.candidate_id, "Backend Engineer", "New Person", [])
    assert feedback == "" and called["n"] == 0
    assert session.query(ProbeRow).filter(ProbeRow.candidate_id == iv.candidate_id).count() == 0
