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

def parse_sitrep_request(payload: dict) -> NormalizedTask:
    task = payload.get("task") or {}
    agent = payload.get("agent") or {}
    return NormalizedTask(
        title=_first(task, ["title"]) or _first(payload, ["title", "task_title"]),
        description=_first(task, ["description", "detail", "details"]) or _first(payload, ["description", "detail"]),
        summary=_first(payload, ["summary", "meeting_summary", "context", "meetingSummary"]),
        attendees=payload.get("attendees") or [],
        instructions=_first(agent, ["instructions"]) or _first(payload, ["instructions", "agent_instructions"]),
        raw=payload,
    )

def artifact_response(title: str, content: str) -> dict:
    return {"artifacts": [{"type": "markdown", "title": title, "content": content}]}
