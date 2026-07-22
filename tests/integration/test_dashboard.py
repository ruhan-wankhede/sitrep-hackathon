from app.config import settings
from app.pipeline.passes import Claim, CompetencyScore, Extraction, FlagSet, ScoreSet
from app.pipeline.persist import save_interview

def _seed(session):
    ext = Extraction(is_interview=True, candidate_name="Aisha Verma", role_title="Backend Engineer",
                     interviewer="Priya", exchanges=[],
                     claims=[Claim(category="team_size", statement="led 8", value="8")])
    ss = ScoreSet(scores=[CompetencyScore(competency="Technical depth", score=4, evidence=["e"], rationale="r")])
    return save_interview(session, ext, ss, FlagSet(), "s", {}, "test", ["Technical depth", "System design"])

def test_home_lists_roles_and_wrong_token_404(client_with_db, session):
    _seed(session)
    ok = client_with_db.get(f"/d/{settings.dashboard_token}")
    assert ok.status_code == 200 and "backend engineer" in ok.text.lower()
    assert client_with_db.get("/d/wrong-token").status_code == 404

def test_matrix_shows_candidate_and_not_assessed(client_with_db, session):
    iv = _seed(session)
    resp = client_with_db.get(f"/d/{settings.dashboard_token}/role/1")
    assert resp.status_code == 200
    assert "aisha verma" in resp.text.lower()
    assert "Not assessed" in resp.text          # System design has no scores

def test_candidate_page_shows_timeline(client_with_db, session):
    _seed(session)
    resp = client_with_db.get(f"/d/{settings.dashboard_token}/candidate/1")
    assert resp.status_code == 200 and "Priya" in resp.text
