import logging

from sqlalchemy.orm import Session

from app.llm import LLMUnavailable
from app.models import Interview, ProbeRow, ScorecardRow
from app.pipeline import passes

logger = logging.getLogger("probes")

def _candidate_interview_ids(session: Session, candidate_id: int) -> list[int]:
    return [iv.id for iv in session.query(Interview).filter(
        Interview.candidate_id == candidate_id).all()]

def _weak_items(session: Session, candidate_id: int) -> list[dict]:
    iv_ids = _candidate_interview_ids(session, candidate_id)
    if not iv_ids:
        return []
    rows = session.query(ScorecardRow).filter(
        ScorecardRow.interview_id.in_(iv_ids), ScorecardRow.score.in_([1, 2])).all()
    seen, out = set(), []
    for r in rows:
        if r.competency in seen:
            continue
        seen.add(r.competency)
        out.append({"competency": r.competency, "score": r.score,
                    "evidence": r.evidence, "rationale": r.rationale})
    return out

def _strengths(session: Session, candidate_id: int) -> list[dict]:
    iv_ids = _candidate_interview_ids(session, candidate_id)
    if not iv_ids:
        return []
    rows = session.query(ScorecardRow).filter(
        ScorecardRow.interview_id.in_(iv_ids), ScorecardRow.score.isnot(None)).all()
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: -(r.score or 0)):
        if r.competency in seen:
            continue
        seen.add(r.competency)
        out.append({"competency": r.competency, "score": r.score,
                    "evidence": "; ".join(r.evidence or []) or r.rationale})
    return out

def refresh_brief(session: Session, candidate_id: int, role_title: str,
                  candidate_name: str, unprobed: list[str]) -> str:
    """Regenerate the next-interviewer probes and a candidate feedback draft from
    the current panel state. Stores probes; returns the feedback email (or "").
    Best-effort: any failure leaves existing probes untouched and never breaks
    the pipeline."""
    weak = _weak_items(session, candidate_id)
    strengths = _strengths(session, candidate_id)
    if not unprobed and not weak and not strengths:
        session.query(ProbeRow).filter(ProbeRow.candidate_id == candidate_id).delete()
        session.commit()
        return ""
    try:
        brief = passes.generate_brief(role_title, candidate_name, unprobed, weak, strengths)
    except (LLMUnavailable, Exception) as e:  # noqa: BLE001 — enrichment must not break ingest
        logger.warning("brief generation skipped: %s", e)
        return ""
    session.query(ProbeRow).filter(ProbeRow.candidate_id == candidate_id).delete()
    for p in brief.probes:
        session.add(ProbeRow(candidate_id=candidate_id, competency=p.competency,
                             question=p.question, reason=p.reason))
    session.commit()
    return brief.feedback_email or ""
