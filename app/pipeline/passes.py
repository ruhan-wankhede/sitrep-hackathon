from pydantic import BaseModel, Field, field_validator

from app.llm import complete_json

_CLAIM_CATS = {"team_size", "tenure", "role_scope", "project_ownership", "metric", "other"}
_FLAG_TYPES = {"leading_question", "non_job_related", "vague_feedback"}

def _slug(v) -> str:
    return str(v or "").strip().lower().replace(" ", "_").replace("-", "_")

class Claim(BaseModel):
    # Not a strict Literal on purpose: an off-vocabulary category from the model
    # must never fail the whole extraction. Normalize, and snap unknowns to "other".
    category: str = "other"
    statement: str
    value: str = ""

    @field_validator("category", mode="before")
    @classmethod
    def _norm_category(cls, v):
        s = _slug(v)
        return s if s in _CLAIM_CATS else "other"

class Exchange(BaseModel):
    question: str
    answer_summary: str

class Extraction(BaseModel):
    is_interview: bool
    candidate_name: str = ""
    role_title: str = ""
    interviewer: str = ""
    exchanges: list[Exchange] = []
    claims: list[Claim] = []

class CompetencyScore(BaseModel):
    competency: str
    score: int | None = Field(None, ge=1, le=4)
    evidence: list[str] = []
    rationale: str = ""

class ScoreSet(BaseModel):
    scores: list[CompetencyScore] = []

class Flag(BaseModel):
    type: str = "vague_feedback"
    excerpt: str = ""
    note: str = ""

    @field_validator("type", mode="before")
    @classmethod
    def _norm_type(cls, v):
        s = _slug(v)
        return s if s in _FLAG_TYPES else "vague_feedback"

class FlagSet(BaseModel):
    flags: list[Flag] = []

_EXTRACT_SYSTEM = """You analyze meeting summaries from a workplace note-taker.
First decide if this meeting was a job interview (a candidate being evaluated for a role).
If it is not an interview, return is_interview=false and leave other fields empty.
If it is, extract exactly what the summary supports — never invent details:
- candidate_name: the person being interviewed
- role_title: the role they are interviewing for
- interviewer: who conducted the interview (pick from attendees if stated)
- exchanges: question/answer pairs actually described
- claims: factual, checkable claims the candidate made about themselves
  (category team_size/tenure/role_scope/project_ownership/metric/other, with a
  short normalized value, e.g. category=team_size value="8")."""

def extract(summary: str, title: str, description: str, attendees: list[str]) -> Extraction:
    prompt = (
        f"Task title: {title}\nTask description: {description}\n"
        f"Attendees: {', '.join(attendees) or 'unknown'}\n\nMeeting summary:\n{summary}"
    )
    return complete_json(prompt, Extraction, system=_EXTRACT_SYSTEM)

_SCORE_SYSTEM = """You are a strict, fair interview assessor.
Score ONLY from the evidence provided — the exchanges and claims below.
For each competency in the rubric output a score:
- 1 = clear negative signal, 2 = weak, 3 = solid, 4 = exceptional
- score=null when the interview produced no real evidence for that competency.
Every non-null score MUST include at least one evidence item: a short quote or
tight paraphrase from the provided material. Never use general impressions."""

def score(extraction: Extraction, rubric: list[str]) -> ScoreSet:
    prompt = (
        f"Rubric competencies: {', '.join(rubric)}\n\n"
        f"Candidate: {extraction.candidate_name} for {extraction.role_title}\n"
        "Exchanges:\n" + "\n".join(f"Q: {e.question}\nA: {e.answer_summary}" for e in extraction.exchanges)
        + "\n\nClaims:\n" + "\n".join(f"- [{c.category}] {c.statement}" for c in extraction.claims)
    )
    return apply_evidence_gate(complete_json(prompt, ScoreSet, system=_SCORE_SYSTEM))

def apply_evidence_gate(scoreset: ScoreSet) -> ScoreSet:
    for s in scoreset.scores:
        if s.score is not None and not any(e.strip() for e in s.evidence):
            s.score = None
            s.rationale = (s.rationale + " (demoted: no supporting evidence)").strip()
    return scoreset

_FLAGS_SYSTEM = """You audit interview quality for compliance and consistency.
From the meeting summary, flag ONLY genuinely problematic moments:
- leading_question: the interviewer telegraphed the desired answer
- non_job_related: topics that create compliance risk (family plans, age,
  nationality, religion, health, marital status)
- vague_feedback: evaluative statements with no behavioral evidence ("great
  culture fit vibes")
Return an empty list when nothing qualifies. Include a short excerpt for each flag."""

def detect_flags(summary: str) -> FlagSet:
    return complete_json(f"Meeting summary:\n{summary}", FlagSet, system=_FLAGS_SYSTEM)

class Probe(BaseModel):
    competency: str
    question: str
    reason: str = ""

class Brief(BaseModel):
    probes: list[Probe] = []
    feedback_email: str = ""

_BRIEF_SYSTEM = """You prepare two things for a hiring team from the panel's evidence so far.

1) probes — questions for the NEXT interviewer:
- one or two per competency, tied to that competency
- for unprobed competencies, questions that surface real signal
- for weak-evidence competencies, target the exact gap (e.g. "they claimed to
  'lead the migration' but gave no specifics — ask who made the architecture call")
- never generic filler; each must be answerable in an interview and produce evidence
- give a one-line reason per question

2) feedback_email — a short, warm draft the recruiter could adapt to send the candidate:
- ground every point in what actually happened in the interviews; strengths first, then growth areas
- concrete and kind, no clichés
- do NOT state a hire/reject decision — that is the recruiter's call
- 120-180 words, first person from the hiring team"""

def generate_brief(role_title: str, candidate_name: str, unprobed: list[str],
                   weak_items: list[dict], strengths: list[dict]) -> Brief:
    weak = "\n".join(
        f"- {w['competency']} (scored {w['score']}/4): {'; '.join(w.get('evidence') or []) or w.get('rationale', '')}"
        for w in weak_items
    ) or "(none)"
    strong = "\n".join(
        f"- {s['competency']} (scored {s['score']}/4): {s.get('evidence', '')}" for s in strengths
    ) or "(none assessed yet)"
    prompt = (
        f"Role: {role_title}\nCandidate: {candidate_name}\n\n"
        f"Unprobed competencies: {', '.join(unprobed) or '(none)'}\n\n"
        f"Weak-evidence competencies:\n{weak}\n\n"
        f"Assessed strengths:\n{strong}"
    )
    return complete_json(prompt, Brief, system=_BRIEF_SYSTEM)
