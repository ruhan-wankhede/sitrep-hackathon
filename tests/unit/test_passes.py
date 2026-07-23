from app.pipeline.passes import (
    Claim, CompetencyScore, Flag, ScoreSet, Extraction, apply_evidence_gate, extract, score,
)
import app.llm as llm

def test_off_vocabulary_category_and_flag_type_snap_to_fallback():
    # An unexpected category from the model must not fail extraction — it snaps to "other".
    assert Claim(category="Leadership Scope", statement="led a team").category == "other"
    assert Claim(category="Team Size", statement="team of 8").category == "team_size"
    assert Flag(type="illegal question", excerpt="x").type == "vague_feedback"
    assert Flag(type="Non Job Related", excerpt="x").type == "non_job_related"

def test_extraction_survives_unknown_claim_category(monkeypatch):
    monkeypatch.setattr(llm, "PROVIDERS", [lambda **kw: {
        "is_interview": True, "candidate_name": "A", "role_title": "Engineer", "interviewer": "P",
        "exchanges": [], "claims": [{"category": "seniority", "statement": "was senior-most", "value": "1"}]}])
    ext = extract("summary", "t", "d", [])
    assert ext.claims[0].category == "other"

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
