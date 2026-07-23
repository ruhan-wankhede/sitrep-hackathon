from collections import defaultdict
from itertools import combinations

from pydantic import BaseModel

from app.llm import complete_json

def coverage(rows: list[dict]) -> dict[str, list[str]]:
    by_comp: dict[str, list] = defaultdict(list)
    for r in rows:
        by_comp[r["competency"]].append(r["score"])
    assessed = [c for c, scores in by_comp.items() if any(s is not None for s in scores)]
    unassessed = [c for c in by_comp if c not in assessed]
    return {"assessed": assessed, "unassessed": unassessed}

def disagreements(rows: list[dict]) -> list[dict]:
    by_comp: dict[str, dict] = defaultdict(dict)
    for r in rows:
        if r["score"] is not None:
            by_comp[r["competency"]][r["interviewer"]] = r["score"]
    out = []
    for comp, scores in by_comp.items():
        if len(scores) >= 2:
            spread = max(scores.values()) - min(scores.values())
            if spread >= 2:
                out.append({"competency": comp, "spread": spread, "scores": scores})
    return out

def composite(cell_averages: list[float]) -> float | None:
    """Overall score for a candidate: the mean of their per-competency panel
    averages, so each competency counts once regardless of how many
    interviewers probed it. None when nothing has been assessed."""
    vals = [v for v in cell_averages if v is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 1)

_BANDS = [(3.5, "Strong hire", "accent"), (2.8, "Hire", "accent"),
          (2.0, "Lean no", "warn"), (0.0, "No hire", "danger")]

def recommendation(comp: float | None, n_assessed: int, blockers: list[str]) -> dict:
    """Evidence-gated hiring verdict. Any blocker (unresolved claim
    contradiction, compliance flag) caps the verdict at 'Needs follow-up'
    regardless of score — the agent never green-lights over an open concern."""
    if comp is None:
        return {"label": "Insufficient data", "tone": "muted",
                "reason": "No competencies assessed yet."}
    if blockers:
        return {"label": "Needs follow-up", "tone": "warn",
                "reason": "Resolve before advancing: " + "; ".join(blockers) + "."}
    label, tone = next((lbl, tn) for cut, lbl, tn in _BANDS if comp >= cut)
    unit = "competency" if n_assessed == 1 else "competencies"
    return {"label": label, "tone": tone,
            "reason": f"Composite {comp}/4 across {n_assessed} assessed {unit}; no blocking concerns."}

def contradiction_candidates(claims: list[dict]) -> list[tuple[dict, dict]]:
    by_cat: dict[str, list] = defaultdict(list)
    for c in claims:
        # "other" is a catch-all bucket — different miscellaneous facts are not
        # contradictions, so never pair them.
        if c.get("value") and c.get("category") != "other":
            by_cat[c["category"]].append(c)
    pairs = []
    for cat, items in by_cat.items():
        for a, b in combinations(items, 2):
            if a["value"] != b["value"] and a["interview_id"] != b["interview_id"]:
                pairs.append((a, b))
    return pairs

class Verdict(BaseModel):
    contradictory: bool

_VERDICT_SYSTEM = (
    "Two statements a job candidate made in different interviews follow. "
    "Answer whether they genuinely contradict each other about the same fact. "
    "Different facts (e.g. team size vs years of experience) are NOT contradictory."
)

def confirm_contradiction(a: dict, b: dict) -> bool:
    prompt = f"Statement 1: {a['statement']}\nStatement 2: {b['statement']}"
    return complete_json(prompt, Verdict, system=_VERDICT_SYSTEM).contradictory
