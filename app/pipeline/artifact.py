from sqlalchemy.orm import Session

from app.analytics import confirm_contradiction, contradiction_candidates, coverage, disagreements
from app.config import settings
from app.llm import LLMUnavailable
from app.models import Candidate, ClaimRow, Interview, ScorecardRow
from app.pipeline.passes import FlagSet, ScoreSet

SCORE_LABELS = {1: "Weak", 2: "Developing", 3: "Solid", 4: "Exceptional"}

_FLAG_TITLES = {"leading_question": "Leading question", "non_job_related": "Non-job-related topic",
                "vague_feedback": "Vague feedback"}

def _md_cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ").strip()

def panel_snapshot(session: Session, interview: Interview) -> dict:
    cand = session.get(Candidate, interview.candidate_id)
    ivs = session.query(Interview).filter(Interview.candidate_id == cand.id).all()
    iv_by_id = {iv.id: iv for iv in ivs}
    rows = [
        {"competency": r.competency, "score": r.score, "interviewer": iv_by_id[r.interview_id].interviewer}
        for r in session.query(ScorecardRow).filter(ScorecardRow.interview_id.in_(list(iv_by_id))).all()
    ]
    claims = [
        {"category": c.category, "statement": c.statement, "value": c.value, "interview_id": c.interview_id}
        for c in session.query(ClaimRow).filter(ClaimRow.candidate_id == cand.id).all()
    ]
    contradictions = []
    for a, b in contradiction_candidates(claims):
        try:
            confirmed = confirm_contradiction(a, b)
        except LLMUnavailable:
            continue
        if confirmed:
            contradictions.append({"a": a["statement"], "b": b["statement"], "categories": a["category"]})
    return {"coverage": coverage(rows), "disagreements": disagreements(rows), "contradictions": contradictions}

def compose_markdown(interview: Interview, scoreset: ScoreSet, flagset: FlagSet, snapshot: dict) -> str:
    lines = [f"## Interview Scorecard — {interview.interviewer or 'interview'}", "",
             "| Competency | Score | Evidence |", "|---|---|---|"]
    for s in scoreset.scores:
        label = f"{s.score} — {SCORE_LABELS[s.score]}" if s.score else "Not assessed"
        ev = "; ".join(s.evidence) if s.evidence else s.rationale or "—"
        lines.append(f"| {_md_cell(s.competency)} | {_md_cell(label)} | {_md_cell(ev)} |")
    if flagset.flags:
        lines += ["", "### ⚠ Interview quality flags"]
        for f in flagset.flags:
            lines.append(f"- **{_FLAG_TITLES[f.type]}**: “{f.excerpt}” — {f.note}")
    cov, dis, con = snapshot["coverage"], snapshot["disagreements"], snapshot["contradictions"]
    lines += ["", "### Panel so far"]
    if cov["unassessed"]:
        lines.append(f"- ◐ Not yet probed by anyone: {', '.join(cov['unassessed'])}")
    for d in dis:
        pretty = ", ".join(f"{k}: {v}" for k, v in d["scores"].items())
        lines.append(f"- ⚡ Interviewers disagree on **{d['competency']}** (spread {d['spread']}: {pretty})")
    for c in con:
        lines.append(f"- ⚠ Claim inconsistency ({c['categories']}): “{c['a']}” vs “{c['b']}”")
    if not (cov["unassessed"] or dis or con):
        lines.append("- ✓ No gaps, disagreements, or claim inconsistencies detected")
    lines += ["", f"[Open the live panel dashboard]({settings.base_url}/d/{settings.dashboard_token})"]
    return "\n".join(lines)
