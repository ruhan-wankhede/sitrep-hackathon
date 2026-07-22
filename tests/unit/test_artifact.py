import app.llm as llm
from app.pipeline.artifact import compose_markdown, panel_snapshot
from app.pipeline.passes import (Claim, CompetencyScore, Extraction, Flag, FlagSet, ScoreSet)
from app.pipeline.persist import save_interview

def _seed(session, name, interviewer, summary, claims, scores):
    ext = Extraction(is_interview=True, candidate_name=name, role_title="Backend Engineer",
                     interviewer=interviewer, exchanges=[], claims=claims)
    ss = ScoreSet(scores=scores)
    return save_interview(session, ext, ss, FlagSet(), summary, {}, "test", ["Technical depth", "System design"])

def test_snapshot_reports_gap_and_confirmed_contradiction(session, monkeypatch):
    monkeypatch.setattr(llm, "PROVIDERS", [lambda **kw: {"contradictory": True}])
    _seed(session, "Aisha", "Priya", "s1",
          [Claim(category="team_size", statement="led a team of 8", value="8")],
          [CompetencyScore(competency="Technical depth", score=4, evidence=["e"], rationale="")])
    iv = _seed(session, "Aisha", "Sam", "s2",
               [Claim(category="team_size", statement="we were 3", value="3")],
               [CompetencyScore(competency="Technical depth", score=2, evidence=["e"], rationale="")])
    snap = panel_snapshot(session, iv)
    assert "System design" in snap["coverage"]["unassessed"]
    assert snap["disagreements"][0]["spread"] == 2
    assert len(snap["contradictions"]) == 1

def test_snapshot_skips_pair_when_llm_unavailable(session, monkeypatch):
    def always_raises(**kw):
        raise llm.LLMUnavailable("provider down")

    monkeypatch.setattr(llm, "PROVIDERS", [always_raises])
    _seed(session, "Aisha", "Priya", "s1",
          [Claim(category="team_size", statement="led a team of 8", value="8")],
          [CompetencyScore(competency="Technical depth", score=4, evidence=["e"], rationale="")])
    iv = _seed(session, "Aisha", "Sam", "s2",
               [Claim(category="team_size", statement="we were 3", value="3")],
               [CompetencyScore(competency="Technical depth", score=2, evidence=["e"], rationale="")])

    snap = panel_snapshot(session, iv)

    assert snap["contradictions"] == []

def test_compose_markdown_contains_key_sections(session):
    iv = _seed(session, "Aisha", "Priya", "s1", [],
               [CompetencyScore(competency="Technical depth", score=3, evidence=["quote"], rationale="r")])
    ss = ScoreSet(scores=[CompetencyScore(competency="Technical depth", score=3, evidence=["quote"], rationale="r")])
    md = compose_markdown(iv, ss, FlagSet(flags=[Flag(type="non_job_related", excerpt="x", note="n")]),
                          {"coverage": {"assessed": ["Technical depth"], "unassessed": ["System design"]},
                           "disagreements": [], "contradictions": []})
    assert "Technical depth" in md and "Solid" in md
    assert "System design" in md            # gap listed
    assert "non_job_related" in md or "Non-job-related" in md
    assert "/d/" in md                       # dashboard link

def test_compose_markdown_escapes_pipes_and_newlines(session):
    iv = _seed(session, "Aisha", "Priya", "s-esc", [],
               [CompetencyScore(competency="Technical depth", score=3, evidence=["a | b\nc"], rationale="r")])
    ss = ScoreSet(scores=[CompetencyScore(competency="Technical depth", score=3, evidence=["a | b\nc"], rationale="r")])
    md = compose_markdown(iv, ss, FlagSet(), {"coverage": {"assessed": [], "unassessed": []}, "disagreements": [], "contradictions": []})
    row = [line for line in md.splitlines() if line.startswith("| Technical depth")][0]
    assert "a \\| b c" in row and "\n" not in row
