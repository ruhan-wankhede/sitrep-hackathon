from pydantic import BaseModel

class NormalizedTask(BaseModel):
    title: str = ""
    description: str = ""
    summary: str = ""
    attendees: list[str] = []
    instructions: str = ""
    raw: dict = {}

def _first(d: dict, keys: list[str], default=""):
    for k in keys:
        v = d.get(k)
        if v:
            return v
    return default

def _attendee_names(raw) -> list[str]:
    """SitRep sends attendees as objects [{id, name}]; older/test payloads use
    plain strings. Normalize both to a list of name strings so downstream code
    can safely join them."""
    names = []
    for a in raw or []:
        if isinstance(a, str):
            if a.strip():
                names.append(a.strip())
        elif isinstance(a, dict):
            n = a.get("name") or a.get("displayName") or a.get("id") or ""
            if str(n).strip():
                names.append(str(n).strip())
    return names

def parse_sitrep_request(payload: dict) -> NormalizedTask:
    task = payload.get("task") or {}
    agent = payload.get("agent") or {}
    return NormalizedTask(
        title=_first(task, ["title"]) or _first(payload, ["title", "task_title"]),
        description=_first(task, ["description", "detail", "details"]) or _first(payload, ["description", "detail"]),
        summary=_first(payload, ["summary", "meeting_summary", "context", "meetingSummary"]),
        attendees=_attendee_names(payload.get("attendees")),
        instructions=_first(agent, ["instructions"]) or _first(payload, ["instructions", "agent_instructions"]),
        raw=payload,
    )

def markdown_artifact(title: str, content: str) -> dict:
    return {"type": "markdown", "title": title, "content": content}

def link_artifact(title: str, url: str) -> dict:
    return {"type": "link", "title": title, "content": url}

def build_response(artifacts: list[dict], logs: list[str] | None = None) -> dict:
    resp: dict = {"artifacts": artifacts}
    if logs:
        resp["logs"] = logs
    return resp

def artifact_response(title: str, content: str) -> dict:
    return build_response([markdown_artifact(title, content)])
