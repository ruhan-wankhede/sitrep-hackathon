import re

DEFAULTS: dict[str, list[str]] = {
    "engineering": ["Technical depth", "System design", "Problem solving", "Communication", "Collaboration"],
    "sales": ["Discovery skills", "Objection handling", "Closing ability", "Communication", "Pipeline discipline"],
    "pm": ["Product sense", "Prioritization", "Stakeholder management", "Analytical thinking", "Communication"],
    "generic": ["Role knowledge", "Problem solving", "Communication", "Ownership", "Collaboration"],
}

_FAMILY_KEYWORDS = {
    "engineering": ["engineer", "developer", "swe", "sre", "devops", "architect"],
    "sales": ["sales", "account executive", "sdr", "bdr"],
    "pm": ["product manager", "product owner"],
}

def resolve_rubric(role_title: str, instructions: str) -> list[str]:
    m = re.search(r"^\s*competencies\s*:\s*(.+)$", instructions or "", re.IGNORECASE | re.MULTILINE)
    if m:
        items = [c.strip() for c in m.group(1).split(",") if c.strip()]
        if items:
            return items
    title = (role_title or "").lower()
    for family, words in _FAMILY_KEYWORDS.items():
        if any(w in title for w in words):
            return DEFAULTS[family]
    return DEFAULTS["generic"]
