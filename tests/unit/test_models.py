from app.models import Role, Candidate, Interview, dedup_hash

def test_round_trip_and_dedup_hash(session):
    role = Role(title="Backend Engineer", rubric={"competencies": ["Technical depth"]}, dashboard_token="tok")
    session.add(role); session.flush()
    cand = Candidate(name="aisha verma", role_id=role.id)
    session.add(cand); session.flush()
    h = dedup_hash("aisha verma", "Priya", "summary text")
    iv = Interview(candidate_id=cand.id, interviewer="Priya", summary="summary text",
                   raw_payload={"a": 1}, source="test", dedup_hash=h)
    session.add(iv); session.commit()
    assert session.query(Interview).one().dedup_hash == h
    assert len(h) == 64

def test_dedup_hash_is_deterministic():
    assert dedup_hash("a", "b", "c") == dedup_hash("a", "b", "c")
    assert dedup_hash("a", "b", "c") != dedup_hash("a", "b", "d")
