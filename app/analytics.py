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

def contradiction_candidates(claims: list[dict]) -> list[tuple[dict, dict]]:
    by_cat: dict[str, list] = defaultdict(list)
    for c in claims:
        if c.get("value"):
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
