from app.pipeline.passes import (
    CompetencyScore, ScoreSet, Extraction, apply_evidence_gate, extract, score,
)
import app.llm as llm

def test_evidence_gate_demotes_unevidenced_scores():
    ss = ScoreSet(scores=[
        CompetencyScore(competency="A", score=4, evidence=["quote"], rationale="ok"),
        CompetencyScore(competency="B", score=3, evidence=[], rationale="vibes"),
        CompetencyScore(competency="C", score=None, evidence=[], rationale=""),
        CompetencyScore(competency="D", score=2, evidence=[" "], rationale="whitespace only"),
    ])
    gated = apply_evidence_gate(ss)
    assert gated.scores[0].score == 4
    assert gated.scores[1].score is None
    assert "demoted" in gated.scores[1].rationale
    assert gated.scores[2].score is None
    assert gated.scores[3].score is None
    assert "demoted" in gated.scores[3].rationale

def test_extract_and_score_call_llm_with_schemas(monkeypatch):
    def fake(**kw):
        if kw["schema"] is Extraction:
            return {"is_interview": True, "candidate_name": "Jane", "role_title": "Backend Engineer",
                    "interviewer": "Sam", "exchanges": [], "claims": []}
        return {"scores": [{"competency": "Technical depth", "score": 3, "evidence": [], "rationale": "x"}]}
    monkeypatch.setattr(llm, "PROVIDERS", [fake])
    ext = extract("summary", "title", "desc", ["Sam", "Jane"])
    assert ext.candidate_name == "Jane"
    ss = score(ext, ["Technical depth"])
    assert ss.scores[0].score is None  # gate demoted empty-evidence score
