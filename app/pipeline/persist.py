from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Candidate, ClaimRow, FlagRow, Interview, Role, ScorecardRow, dedup_hash
from app.pipeline.passes import Extraction, FlagSet, ScoreSet

def _get_or_create_role(session: Session, title: str, rubric: list[str]) -> Role:
    norm = title.strip().lower() or "unknown role"
    role = session.query(Role).filter(Role.title == norm).one_or_none()
    if role is None:
        role = Role(title=norm, rubric={"competencies": rubric}, dashboard_token=settings.dashboard_token)
        session.add(role)
        session.flush()
    return role

def _get_or_create_candidate(session: Session, name: str, role_id: int) -> Candidate:
    norm = name.strip().lower() or "unknown candidate"
    cand = session.query(Candidate).filter(Candidate.name == norm, Candidate.role_id == role_id).one_or_none()
    if cand is None:
        cand = Candidate(name=norm, role_id=role_id)
        session.add(cand)
        session.flush()
    return cand

def _find_by_hash(session: Session, h: str) -> Interview | None:
    return session.query(Interview).filter(Interview.dedup_hash == h).one_or_none()

def _attempt(session: Session, extraction: Extraction, scoreset: ScoreSet, flagset: FlagSet,
            summary: str, raw_payload: dict, source: str, rubric: list[str]) -> Interview:
    role = _get_or_create_role(session, extraction.role_title, rubric)
    cand = _get_or_create_candidate(session, extraction.candidate_name, role.id)
    h = dedup_hash(extraction.candidate_name, extraction.interviewer, summary)
    iv = _find_by_hash(session, h)
    if iv is None:
        iv = Interview(candidate_id=cand.id, interviewer=extraction.interviewer, summary=summary,
                       raw_payload=raw_payload, source=source, dedup_hash=h)
        session.add(iv)
        session.flush()
    else:
        for model in (ScorecardRow, ClaimRow, FlagRow):
            session.query(model).filter(model.interview_id == iv.id).delete()
        iv.summary, iv.raw_payload, iv.source = summary, raw_payload, source
    rubric_by_norm = {r.casefold().strip(): r for r in rubric}
    scored_norms = set()
    for s in scoreset.scores:
        norm = s.competency.casefold().strip()
        scored_norms.add(norm)
        canonical = rubric_by_norm.get(norm, s.competency)
        session.add(ScorecardRow(interview_id=iv.id, competency=canonical, score=s.score,
                                 evidence=s.evidence, rationale=s.rationale))
    for competency in rubric:
        if competency.casefold().strip() not in scored_norms:
            session.add(ScorecardRow(interview_id=iv.id, competency=competency, score=None))
    for c in extraction.claims:
        session.add(ClaimRow(candidate_id=cand.id, interview_id=iv.id, category=c.category,
                             statement=c.statement, value=c.value))
    for f in flagset.flags:
        session.add(FlagRow(interview_id=iv.id, type=f.type, excerpt=f.excerpt, note=f.note))
    session.commit()
    return iv

def save_interview(session: Session, extraction: Extraction, scoreset: ScoreSet, flagset: FlagSet,
                   summary: str, raw_payload: dict, source: str, rubric: list[str]) -> Interview:
    try:
        return _attempt(session, extraction, scoreset, flagset, summary, raw_payload, source, rubric)
    except IntegrityError:
        session.rollback()
        return _attempt(session, extraction, scoreset, flagset, summary, raw_payload, source, rubric)
