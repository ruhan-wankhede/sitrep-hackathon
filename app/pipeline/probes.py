import logging

from sqlalchemy.orm import Session

from app.llm import LLMUnavailable
from app.models import Interview, ProbeRow, ScorecardRow
from app.pipeline import passes

logger = logging.getLogger("probes")

def _weak_items(session: Session, candidate_id: int) -> list[dict]:
    iv_ids = [iv.id for iv in session.query(Interview).filter(
        Interview.candidate_id == candidate_id).all()]
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

def refresh_probes(session: Session, candidate_id: int, role_title: str,
                   candidate_name: str, unprobed: list[str]) -> None:
    """Regenerate the next-interviewer brief for a candidate from the current
    panel state. Best-effort: any failure leaves existing probes untouched and
    never breaks the pipeline."""
    weak = _weak_items(session, candidate_id)
    if not unprobed and not weak:
        session.query(ProbeRow).filter(ProbeRow.candidate_id == candidate_id).delete()
        session.commit()
        return
    try:
        result = passes.probe_questions(role_title, candidate_name, unprobed, weak)
    except (LLMUnavailable, Exception) as e:  # noqa: BLE001 — enrichment must not break ingest
        logger.warning("probe generation skipped: %s", e)
        return
    session.query(ProbeRow).filter(ProbeRow.candidate_id == candidate_id).delete()
    for p in result.probes:
        session.add(ProbeRow(candidate_id=candidate_id, competency=p.competency,
                             question=p.question, reason=p.reason))
    session.commit()
