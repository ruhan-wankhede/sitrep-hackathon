from app.models import Candidate, ClaimRow, Interview, ScorecardRow
from app.pipeline import persist
from app.pipeline.passes import Claim, CompetencyScore, Extraction, Flag, FlagSet, ScoreSet
from app.pipeline.persist import save_interview

EXT = Extraction(is_interview=True, candidate_name="Aisha Verma", role_title="Backend Engineer",
                 interviewer="Priya", exchanges=[],
                 claims=[Claim(category="team_size", statement="led a team of 8", value="8")])
SS = ScoreSet(scores=[CompetencyScore(competency="Technical depth", score=3, evidence=["q"], rationale="r")])
FS = FlagSet(flags=[Flag(type="vague_feedback", excerpt="vibes", note="n")])

def test_save_creates_role_candidate_interview_and_children(session):
    iv = save_interview(session, EXT, SS, FS, "summary", {"raw": 1}, "test", ["Technical depth"])
    assert iv.id is not None
    assert session.query(Candidate).one().name == "aisha verma"
    assert session.query(ScorecardRow).count() == 1
    assert session.query(ClaimRow).one().value == "8"

def test_save_is_idempotent_on_same_summary(session):
    save_interview(session, EXT, SS, FS, "summary", {}, "test", ["Technical depth"])
    save_interview(session, EXT, SS, FS, "summary", {}, "test", ["Technical depth"])
    assert session.query(Interview).count() == 1
    assert session.query(ScorecardRow).count() == 1

def test_save_recovers_from_concurrent_duplicate_insert(session, monkeypatch):
    first = save_interview(session, EXT, SS, FS, "summary", {}, "test", ["Technical depth"])

    real_find_by_hash = persist._find_by_hash
    calls = {"n": 0}

    def flaky_find_by_hash(session, h):
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return real_find_by_hash(session, h)

    monkeypatch.setattr(persist, "_find_by_hash", flaky_find_by_hash)

    iv = save_interview(session, EXT, SS, FS, "summary", {}, "test", ["Technical depth"])

    assert iv.id == first.id
    assert session.query(Interview).count() == 1
