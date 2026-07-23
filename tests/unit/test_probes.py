import app.llm as llm
from app.models import ProbeRow
from app.pipeline.passes import CompetencyScore, Extraction, FlagSet, ScoreSet
from app.pipeline.persist import save_interview
from app.pipeline.probes import refresh_probes

RUBRIC = ["Technical depth", "System design"]

def _seed_weak(session):
    ext = Extraction(is_interview=True, candidate_name="Aisha Verma", role_title="Backend Engineer",
                     interviewer="Priya", exchanges=[], claims=[])
    ss = ScoreSet(scores=[CompetencyScore(competency="Technical depth", score=2,
                                          evidence=["was vague on throughput"], rationale="thin")])
    return save_interview(session, ext, ss, FlagSet(), "s1", {}, "test", RUBRIC)

def test_refresh_probes_writes_rows_from_llm(session, monkeypatch):
    iv = _seed_weak(session)
    monkeypatch.setattr(llm, "PROVIDERS", [lambda **kw: {"probes": [
        {"competency": "System design", "question": "Design a rate limiter.", "reason": "unprobed"},
        {"competency": "Technical depth", "question": "Who owned the migration call?", "reason": "vague evidence"},
    ]}])
    refresh_probes(session, iv.candidate_id, "Backend Engineer", "Aisha Verma", ["System design"])
    rows = session.query(ProbeRow).filter(ProbeRow.candidate_id == iv.candidate_id).all()
    assert {r.competency for r in rows} == {"System design", "Technical depth"}

def test_refresh_probes_clears_when_no_gaps_or_weak(session, monkeypatch):
    ext = Extraction(is_interview=True, candidate_name="Daniel Okafor", role_title="Backend Engineer",
                     interviewer="Sam", exchanges=[], claims=[])
    ss = ScoreSet(scores=[CompetencyScore(competency="Technical depth", score=4, evidence=["e"], rationale=""),
                          CompetencyScore(competency="System design", score=4, evidence=["e"], rationale="")])
    iv = save_interview(session, ext, ss, FlagSet(), "s2", {}, "test", RUBRIC)
    session.add(ProbeRow(candidate_id=iv.candidate_id, competency="X", question="stale", reason=""))
    session.commit()
    called = {"n": 0}
    def fake(**kw):
        called["n"] += 1
        return {"probes": []}
    monkeypatch.setattr(llm, "PROVIDERS", [fake])
    refresh_probes(session, iv.candidate_id, "Backend Engineer", "Daniel Okafor", [])
    assert session.query(ProbeRow).filter(ProbeRow.candidate_id == iv.candidate_id).count() == 0
    assert called["n"] == 0  # no LLM call when nothing to probe
