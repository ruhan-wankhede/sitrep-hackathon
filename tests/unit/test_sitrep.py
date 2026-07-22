from app.sitrep import parse_sitrep_request, artifact_response

REFERENCE_SHAPE = {
    "task": {"title": "Interview debrief", "description": "Score the candidate"},
    "summary": "We interviewed Jane...",
    "attendees": ["Sam", "Jane Doe"],
    "agent": {"instructions": "competencies: coding, communication"},
}

def test_parses_reference_shape():
    n = parse_sitrep_request(REFERENCE_SHAPE)
    assert n.title == "Interview debrief"
    assert n.summary.startswith("We interviewed")
    assert n.instructions == "competencies: coding, communication"
    assert n.attendees == ["Sam", "Jane Doe"]
    assert n.raw == REFERENCE_SHAPE

def test_tolerates_flat_and_missing_fields():
    n = parse_sitrep_request({"title": "t", "meeting_summary": "s"})
    assert n.title == "t" and n.summary == "s"
    assert n.description == "" and n.instructions == "" and n.attendees == []

def test_artifact_response_envelope():
    r = artifact_response("T", "C")
    assert r == {"artifacts": [{"type": "markdown", "title": "T", "content": "C"}]}
