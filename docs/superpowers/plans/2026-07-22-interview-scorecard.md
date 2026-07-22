# Interview Scorecard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A SitRep code-track agent (FastAPI service) that turns interview meeting summaries into evidence-gated scorecards, tracks claim consistency across interviews, and serves a candidate comparison dashboard.

**Architecture:** One FastAPI app: `POST /run|/test` (SitRep contract) feed a staged pipeline — three schema-validated LLM calls (extract / score / flags) through a provider-agnostic `complete_json()` (Gemini free tier primary, Groq free fallback) — then plain-Python analytics (coverage, disagreements, claim contradictions) over Neon Postgres, returning markdown artifacts with a link to a Jinja2+Tailwind dashboard.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2, google-genai, httpx (Groq), Jinja2, Tailwind+Alpine via CDN, pytest. Hosting: Render free + UptimeRobot. DB: Neon free Postgres (SQLite in tests).

## Global Constraints

- No paid services anywhere: Gemini free tier (`gemini-2.5-flash`), Groq free tier (`llama-3.3-70b-versatile`), Render free, Neon free, UptimeRobot free.
- SitRep contract (verify wire format empirically in Task 3): request carries task title/description, meeting summary (NOT transcript), attendees, `agent.instructions`; response is `{"artifacts": [{"type": "markdown", "title": str, "content": str}]}`.
- Evidence gate is non-negotiable: a competency score with empty evidence is demoted to "not assessed" (score=None) in code.
- Never return HTTP 500 to SitRep: LLM failure → graceful markdown artifact.
- Single-tenant fallback: one deployment, one `DASHBOARD_TOKEN` env var gating all `/d/{token}` routes.
- All LLM outputs validated against Pydantic schemas; validation failure = failed attempt (retry/fallback).
- Commit style: Conventional Commits, no AI references (user rule GH-2).
- Repo must end up public with MIT LICENSE, README setup + deployment instructions (Kaggle code-track requirement).
- Python: sync code throughout (no async) — simpler to test, latency is LLM-bound.

## File Structure

```
SitrepHackathon/
├── app/
│   ├── __init__.py
│   ├── main.py               # FastAPI app, /run /test /healthz, wiring
│   ├── config.py             # pydantic-settings env config
│   ├── db.py                 # engine/session factory
│   ├── models.py             # SQLAlchemy: Role, Candidate, Interview, ScorecardRow, ClaimRow, FlagRow
│   ├── sitrep.py             # tolerant request normalizer + artifact response builder
│   ├── llm/
│   │   ├── __init__.py       # complete_json() — the ONLY LLM entry point
│   │   ├── gemini.py         # provider: Gemini
│   │   └── groq.py           # provider: Groq (OpenAI-compatible REST via httpx)
│   ├── rubrics.py            # default rubrics + instructions override + role-family match
│   ├── pipeline/
│   │   ├── __init__.py       # run_pipeline() orchestrator
│   │   ├── passes.py         # LLM passes ①②③: schemas + prompts + evidence gate
│   │   ├── persist.py        # upsert interview + child rows (dedup hash)
│   │   └── artifact.py       # markdown artifact composition
│   ├── analytics.py          # coverage, disagreement, claim contradictions (pure funcs)
│   └── web/
│       ├── routes.py         # /d/{token} dashboard routes
│       └── templates/        # base.html, home.html, matrix.html, candidate.html
├── tests/
│   ├── conftest.py           # in-memory SQLite session, FakeLLM
│   ├── unit/                 # test_rubrics.py, test_passes.py, test_analytics.py, test_sitrep.py
│   └── integration/          # test_run_flow.py (TestClient, faked LLM)
├── fixtures/interviews/      # 5 seed payloads (candidate A ×3, candidate B ×2)
├── scripts/seed.py           # POST fixtures to a running instance's /test
├── requirements.txt, .env.example, render.yaml, LICENSE, README.md, .gitignore
```

---

### Task 1: Scaffold, config, healthz

**Files:**
- Create: `requirements.txt`, `.gitignore`, `.env.example`, `app/__init__.py`, `app/config.py`, `app/main.py`
- Test: `tests/unit/test_health.py`

**Interfaces:**
- Produces: `app.config.settings` (fields: `gemini_api_key: str`, `groq_api_key: str`, `database_url: str`, `dashboard_token: str`, `base_url: str`); `app.main.app` (FastAPI instance with `GET /healthz` → `{"ok": true}`).

- [ ] **Step 1: Write requirements.txt and .gitignore**

`requirements.txt`:
```
fastapi>=0.110
uvicorn[standard]>=0.29
pydantic>=2.7
pydantic-settings>=2.2
sqlalchemy>=2.0
psycopg2-binary>=2.9
google-genai>=1.0
httpx>=0.27
jinja2>=3.1
pytest>=8.0
```

`.gitignore`:
```
.venv/
__pycache__/
.env
*.pyc
.pytest_cache/
```

`.env.example`:
```
GEMINI_API_KEY=your-key-from-aistudio.google.com
GROQ_API_KEY=your-key-from-console.groq.com
DATABASE_URL=postgresql+psycopg2://user:pass@host/db   # Neon connection string; sqlite:///local.db for local
DASHBOARD_TOKEN=generate-a-long-random-string
BASE_URL=http://localhost:8000
```

- [ ] **Step 2: Create venv and install**

Run: `cd C:\Users\ruhan\PycharmProjects\SitrepHackathon; py -3.12 -m venv .venv; .venv\Scripts\pip install -r requirements.txt`
Expected: installs succeed.

- [ ] **Step 3: Write the failing test**

`tests/unit/test_health.py`:
```python
from fastapi.testclient import TestClient
from app.main import app

def test_healthz_returns_ok():
    client = TestClient(app)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
```

- [ ] **Step 4: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/unit/test_health.py -v`
Expected: FAIL (ModuleNotFoundError: app).

- [ ] **Step 5: Implement config and app**

`app/__init__.py`: empty file.

`app/config.py`:
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    gemini_api_key: str = ""
    groq_api_key: str = ""
    database_url: str = "sqlite:///local.db"
    dashboard_token: str = "dev-token"
    base_url: str = "http://localhost:8000"

    model_config = {"env_file": ".env"}

settings = Settings()
```

`app/main.py`:
```python
from fastapi import FastAPI

app = FastAPI(title="Interview Scorecard")

@app.get("/healthz")
def healthz():
    return {"ok": True}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/unit/test_health.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .gitignore .env.example app tests
git commit -m "feat: scaffold fastapi app with config and healthz"
```

---

### Task 2: LLM layer with provider fallback

**Files:**
- Create: `app/llm/__init__.py`, `app/llm/gemini.py`, `app/llm/groq.py`
- Test: `tests/unit/test_llm.py`

**Interfaces:**
- Consumes: `app.config.settings`.
- Produces: `app.llm.complete_json(prompt: str, schema: type[BaseModel], system: str = "") -> BaseModel` (validated instance); raises `app.llm.LLMUnavailable` after all providers/retries fail. Module attribute `app.llm.PROVIDERS: list` (monkeypatchable in tests). Each provider module exposes `complete(prompt: str, system: str, schema: type[BaseModel]) -> dict`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_llm.py`:
```python
import pytest
from pydantic import BaseModel
import app.llm as llm

class Out(BaseModel):
    x: int

def test_returns_validated_model_from_first_provider(monkeypatch):
    monkeypatch.setattr(llm, "PROVIDERS", [lambda **kw: {"x": 1}])
    assert llm.complete_json("p", Out).x == 1

def test_falls_back_when_first_provider_fails(monkeypatch):
    def bad(**kw): raise RuntimeError("quota")
    monkeypatch.setattr(llm, "PROVIDERS", [bad, lambda **kw: {"x": 2}])
    monkeypatch.setattr(llm, "RETRY_SLEEP", 0)
    assert llm.complete_json("p", Out).x == 2

def test_invalid_json_counts_as_failure(monkeypatch):
    monkeypatch.setattr(llm, "PROVIDERS", [lambda **kw: {"x": "not-an-int-fixable"}, lambda **kw: {"wrong": 1}])
    monkeypatch.setattr(llm, "RETRY_SLEEP", 0)
    # first provider coerces "not-an-int-fixable"? no — pydantic strict enough to fail, falls to second, also fails
    with pytest.raises(llm.LLMUnavailable):
        llm.complete_json("p", Out)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/unit/test_llm.py -v`
Expected: FAIL (no module app.llm).

- [ ] **Step 3: Implement**

`app/llm/__init__.py`:
```python
import time
from pydantic import BaseModel, ValidationError

class LLMUnavailable(Exception):
    pass

RETRY_SLEEP = 1.5
ATTEMPTS_PER_PROVIDER = 2

def _load_providers():
    from app.llm import gemini, groq
    return [gemini.complete, groq.complete]

PROVIDERS = None  # lazy; tests monkeypatch this

def complete_json(prompt: str, schema: type[BaseModel], system: str = "") -> BaseModel:
    providers = PROVIDERS if PROVIDERS is not None else _load_providers()
    last_err = None
    for provider in providers:
        for attempt in range(ATTEMPTS_PER_PROVIDER):
            try:
                raw = provider(prompt=prompt, system=system, schema=schema)
                return schema.model_validate(raw)
            except (Exception, ValidationError) as e:
                last_err = e
                time.sleep(RETRY_SLEEP * (attempt + 1))
    raise LLMUnavailable(f"all providers failed: {last_err}")
```

`app/llm/gemini.py`:
```python
import json
from google import genai
from app.config import settings

MODEL = "gemini-2.5-flash"

def complete(prompt: str, system: str, schema) -> dict:
    client = genai.Client(api_key=settings.gemini_api_key)
    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={
            "system_instruction": system or None,
            "response_mime_type": "application/json",
            "response_schema": schema,
        },
    )
    return json.loads(resp.text)
```

`app/llm/groq.py`:
```python
import json
import httpx
from app.config import settings

MODEL = "llama-3.3-70b-versatile"
URL = "https://api.groq.com/openai/v1/chat/completions"

def complete(prompt: str, system: str, schema) -> dict:
    schema_hint = json.dumps(schema.model_json_schema())
    messages = [
        {"role": "system", "content": (system + "\n\nRespond ONLY with JSON matching this schema:\n" + schema_hint).strip()},
        {"role": "user", "content": prompt},
    ]
    resp = httpx.post(
        URL,
        headers={"Authorization": f"Bearer {settings.groq_api_key}"},
        json={"model": MODEL, "messages": messages, "response_format": {"type": "json_object"}, "temperature": 0.2},
        timeout=60,
    )
    resp.raise_for_status()
    return json.loads(resp.json()["choices"][0]["message"]["content"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest tests/unit/test_llm.py -v`
Expected: PASS (3 tests). If the coercion test surprises (Pydantic lax int coercion), change `Out.x` assertion input to `{"x": "abc"}` so validation genuinely fails.

- [ ] **Step 5: Commit**

```bash
git add app/llm tests/unit/test_llm.py
git commit -m "feat: provider-agnostic llm layer with gemini primary and groq fallback"
```

---

### Task 3: SitRep request normalizer + stub /run and /test

**Files:**
- Create: `app/sitrep.py`
- Modify: `app/main.py`
- Test: `tests/unit/test_sitrep.py`, `tests/integration/test_endpoints_stub.py`

**Interfaces:**
- Produces: `app.sitrep.NormalizedTask` (Pydantic: `title: str`, `description: str`, `summary: str`, `attendees: list[str]`, `instructions: str`, `raw: dict`); `app.sitrep.parse_sitrep_request(payload: dict) -> NormalizedTask`; `app.sitrep.artifact_response(title: str, content: str) -> dict` returning the SitRep artifacts envelope. `POST /run` and `POST /test` accept any JSON dict, log it, return an artifact envelope.

**Note:** The normalizer is deliberately tolerant of several plausible field spellings because the exact wire format is verified empirically at the end of this task (Studio → ngrok). Adjust the candidate key lists after capture — that is Step 8.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_sitrep.py`:
```python
from app.sitrep import parse_sitrep_request, artifact_response

REFERENCE_SHAPE = {
    "task": {"title": "Interview debrief", "description": "Score the candidate"},
    "summary": "We interviewed Jane...",
    "attendees": ["Sam", "Jane Doe"],
    "agent": {"instructions": "competencies: coding, communication"},
}

def test_parses_reference_shape():
    n = parse_sitrep_request(REFERENCE_SHAPE)
    assert n.title == "Interview debrief"
    assert n.summary.startswith("We interviewed")
    assert n.instructions == "competencies: coding, communication"
    assert n.attendees == ["Sam", "Jane Doe"]
    assert n.raw == REFERENCE_SHAPE

def test_tolerates_flat_and_missing_fields():
    n = parse_sitrep_request({"title": "t", "meeting_summary": "s"})
    assert n.title == "t" and n.summary == "s"
    assert n.description == "" and n.instructions == "" and n.attendees == []

def test_artifact_response_envelope():
    r = artifact_response("T", "C")
    assert r == {"artifacts": [{"type": "markdown", "title": "T", "content": "C"}]}
```

`tests/integration/test_endpoints_stub.py`:
```python
from fastapi.testclient import TestClient
from app.main import app

def test_run_and_test_accept_json_and_return_artifacts():
    client = TestClient(app)
    for path in ("/run", "/test"):
        resp = client.post(path, json={"task": {"title": "x"}, "summary": "y"})
        assert resp.status_code == 200
        body = resp.json()
        assert "artifacts" in body and body["artifacts"][0]["type"] == "markdown"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/unit/test_sitrep.py tests/integration/test_endpoints_stub.py -v`
Expected: FAIL (no app.sitrep; 404 on /run).

- [ ] **Step 3: Implement**

`app/sitrep.py`:
```python
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
```

Modify `app/main.py` to:
```python
import json
import logging
from fastapi import FastAPI, Request

from app.sitrep import parse_sitrep_request, artifact_response

logger = logging.getLogger("sitrep")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Interview Scorecard")

@app.get("/healthz")
def healthz():
    return {"ok": True}

async def _handle(request: Request, source: str) -> dict:
    payload = await request.json()
    logger.info("WIRE_CAPTURE %s %s", source, json.dumps(payload)[:4000])
    normalized = parse_sitrep_request(payload)
    return artifact_response("Interview Scorecard", f"Received task: {normalized.title or '(untitled)'}")

@app.post("/run")
async def run(request: Request):
    return await _handle(request, "run")

@app.post("/test")
async def test(request: Request):
    return await _handle(request, "test")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest tests/unit/test_sitrep.py tests/integration/test_endpoints_stub.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/sitrep.py app/main.py tests
git commit -m "feat: sitrep request normalizer and stub run/test endpoints with wire logging"
```

- [ ] **Step 6: Start the app locally + ngrok tunnel**

Run (terminal 1): `.venv\Scripts\uvicorn app.main:app --port 8000`
Run (terminal 2): `ngrok http 8000` (install from ngrok.com free tier if absent). Copy the https URL.

- [ ] **Step 7: Point SitRep Studio at the tunnel and fire tests**

In app.joinsitrep.com → Studio → the saved "Interview Scorecard" draft → Build step → set Endpoint URL to the ngrok https URL → Test step → Run all three generated tests. Confirm each returns the stub artifact in the Studio UI.

- [ ] **Step 8: Capture the real wire format and adjust**

Read the `WIRE_CAPTURE` log lines from terminal 1. Record: exact field names, any workspace/install identifier (also check ngrok's inspector at http://127.0.0.1:4040 for headers), and observed timeout behavior. Update `parse_sitrep_request` key lists and `tests/unit/test_sitrep.py::REFERENCE_SHAPE` to the real shape. Re-run Step 4 tests. Commit:

```bash
git add app/sitrep.py tests/unit/test_sitrep.py
git commit -m "fix: align request parsing with captured sitrep wire format"
```

---

### Task 4: Database models and session

**Files:**
- Create: `app/db.py`, `app/models.py`
- Test: `tests/conftest.py`, `tests/unit/test_models.py`

**Interfaces:**
- Produces: `app.db.get_engine()`, `app.db.SessionLocal` (sessionmaker), `app.db.init_db(engine)` (create_all), `app.db.bind_default_engine()`. Models per spec §5: `Role(id, title, rubric: JSON, dashboard_token, created_at)`, `Candidate(id, name, role_id, created_at)`, `Interview(id, candidate_id, interviewer, meeting_date, summary, raw_payload: JSON, source, dedup_hash UNIQUE, created_at)`, `ScorecardRow(id, interview_id, competency, score: int|None, evidence: JSON, rationale)`, `ClaimRow(id, candidate_id, interview_id, category, statement, value)`, `FlagRow(id, interview_id, type, excerpt, note)`. Helper `app.models.dedup_hash(candidate: str, interviewer: str, summary: str) -> str` (sha256 hex).

- [ ] **Step 1: Write conftest and failing test**

`tests/conftest.py`:
```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import init_db

@pytest.fixture()
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    init_db(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()
```

`tests/unit/test_models.py`:
```python
from app.models import Role, Candidate, Interview, dedup_hash

def test_round_trip_and_dedup_hash(session):
    role = Role(title="Backend Engineer", rubric={"competencies": ["Technical depth"]}, dashboard_token="tok")
    session.add(role); session.flush()
    cand = Candidate(name="aisha verma", role_id=role.id)
    session.add(cand); session.flush()
    h = dedup_hash("aisha verma", "Priya", "summary text")
    iv = Interview(candidate_id=cand.id, interviewer="Priya", summary="summary text",
                   raw_payload={"a": 1}, source="test", dedup_hash=h)
    session.add(iv); session.commit()
    assert session.query(Interview).one().dedup_hash == h
    assert len(h) == 64

def test_dedup_hash_is_deterministic():
    assert dedup_hash("a", "b", "c") == dedup_hash("a", "b", "c")
    assert dedup_hash("a", "b", "c") != dedup_hash("a", "b", "d")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/unit/test_models.py -v`
Expected: FAIL (no app.db / app.models).

- [ ] **Step 3: Implement**

`app/db.py`:
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings

class Base(DeclarativeBase):
    pass

def get_engine():
    return create_engine(settings.database_url, pool_pre_ping=True)

def init_db(engine):
    from app import models  # noqa: F401 — register tables
    Base.metadata.create_all(engine)

SessionLocal = sessionmaker()

def bind_default_engine():
    engine = get_engine()
    init_db(engine)
    SessionLocal.configure(bind=engine)
    return engine
```

`app/models.py`:
```python
import hashlib
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

def _now():
    return datetime.now(timezone.utc)

def dedup_hash(candidate: str, interviewer: str, summary: str) -> str:
    key = f"{candidate.strip().lower()}|{interviewer.strip().lower()}|{summary.strip()}"
    return hashlib.sha256(key.encode()).hexdigest()

class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    rubric: Mapped[dict] = mapped_column(JSON)
    dashboard_token: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(default=_now)

class Candidate(Base):
    __tablename__ = "candidates"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    created_at: Mapped[datetime] = mapped_column(default=_now)

class Interview(Base):
    __tablename__ = "interviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"))
    interviewer: Mapped[str] = mapped_column(String(200), default="")
    meeting_date: Mapped[datetime] = mapped_column(default=_now)
    summary: Mapped[str] = mapped_column(Text)
    raw_payload: Mapped[dict] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(10))
    dedup_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)

class ScorecardRow(Base):
    __tablename__ = "scorecards"
    id: Mapped[int] = mapped_column(primary_key=True)
    interview_id: Mapped[int] = mapped_column(ForeignKey("interviews.id"))
    competency: Mapped[str] = mapped_column(String(200))
    score: Mapped[int | None] = mapped_column(nullable=True)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    rationale: Mapped[str] = mapped_column(Text, default="")

class ClaimRow(Base):
    __tablename__ = "claims"
    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"))
    interview_id: Mapped[int] = mapped_column(ForeignKey("interviews.id"))
    category: Mapped[str] = mapped_column(String(40))
    statement: Mapped[str] = mapped_column(Text)
    value: Mapped[str] = mapped_column(String(200), default="")

class FlagRow(Base):
    __tablename__ = "flags"
    id: Mapped[int] = mapped_column(primary_key=True)
    interview_id: Mapped[int] = mapped_column(ForeignKey("interviews.id"))
    type: Mapped[str] = mapped_column(String(40))
    excerpt: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest tests/unit/test_models.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/db.py app/models.py tests/conftest.py tests/unit/test_models.py
git commit -m "feat: sqlalchemy models with dedup hash and test session fixture"
```

---

### Task 5: Rubrics — defaults, role-family match, instructions override

**Files:**
- Create: `app/rubrics.py`
- Test: `tests/unit/test_rubrics.py`

**Interfaces:**
- Produces: `app.rubrics.resolve_rubric(role_title: str, instructions: str) -> list[str]` (ordered competency names). `app.rubrics.DEFAULTS: dict[str, list[str]]` with keys `engineering`, `sales`, `pm`, `generic`.

**Override syntax (document in marketplace listing):** a line in the agent's Instructions field like `competencies: X, Y, Z` wins over defaults.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_rubrics.py`:
```python
from app.rubrics import resolve_rubric, DEFAULTS

def test_instructions_override_wins():
    r = resolve_rubric("Backend Engineer", "Be strict.\ncompetencies: Kubernetes, GraphQL, Mentoring")
    assert r == ["Kubernetes", "GraphQL", "Mentoring"]

def test_engineering_family_matched_from_title():
    assert resolve_rubric("Senior Backend Engineer", "") == DEFAULTS["engineering"]
    assert resolve_rubric("Software Developer", "") == DEFAULTS["engineering"]

def test_sales_and_pm_families():
    assert resolve_rubric("Account Executive", "") == DEFAULTS["sales"]
    assert resolve_rubric("Product Manager", "") == DEFAULTS["pm"]

def test_unknown_title_falls_back_to_generic():
    assert resolve_rubric("Chief Vibes Officer", "") == DEFAULTS["generic"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/unit/test_rubrics.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

`app/rubrics.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest tests/unit/test_rubrics.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/rubrics.py tests/unit/test_rubrics.py
git commit -m "feat: rubric resolution with role-family defaults and instructions override"
```

---

### Task 6: Pipeline passes — schemas, prompts, evidence gate

**Files:**
- Create: `app/pipeline/__init__.py` (empty until Task 9), `app/pipeline/passes.py`
- Test: `tests/unit/test_passes.py`

**Interfaces:**
- Consumes: `app.llm.complete_json`.
- Produces (all in `app.pipeline.passes`): Pydantic models `Claim(category, statement, value)`, `Exchange(question, answer_summary)`, `Extraction(is_interview, candidate_name, role_title, interviewer, exchanges, claims)`, `CompetencyScore(competency, score: int|None, evidence: list[str], rationale)`, `ScoreSet(scores)`, `Flag(type, excerpt, note)`, `FlagSet(flags)`. Functions: `extract(summary: str, title: str, description: str, attendees: list[str]) -> Extraction`; `score(extraction: Extraction, rubric: list[str]) -> ScoreSet` (evidence gate applied); `detect_flags(summary: str) -> FlagSet`; `apply_evidence_gate(scoreset: ScoreSet) -> ScoreSet` (pure).

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_passes.py`:
```python
from app.pipeline.passes import (
    CompetencyScore, ScoreSet, Extraction, apply_evidence_gate, extract, score,
)
import app.llm as llm

def test_evidence_gate_demotes_unevidenced_scores():
    ss = ScoreSet(scores=[
        CompetencyScore(competency="A", score=4, evidence=["quote"], rationale="ok"),
        CompetencyScore(competency="B", score=3, evidence=[], rationale="vibes"),
        CompetencyScore(competency="C", score=None, evidence=[], rationale=""),
    ])
    gated = apply_evidence_gate(ss)
    assert gated.scores[0].score == 4
    assert gated.scores[1].score is None
    assert "demoted" in gated.scores[1].rationale
    assert gated.scores[2].score is None

def test_extract_and_score_call_llm_with_schemas(monkeypatch):
    def fake(**kw):
        if kw["schema"] is Extraction:
            return {"is_interview": True, "candidate_name": "Jane", "role_title": "Backend Engineer",
                    "interviewer": "Sam", "exchanges": [], "claims": []}
        return {"scores": [{"competency": "Technical depth", "score": 3, "evidence": [], "rationale": "x"}]}
    monkeypatch.setattr(llm, "PROVIDERS", [fake])
    ext = extract("summary", "title", "desc", ["Sam", "Jane"])
    assert ext.candidate_name == "Jane"
    ss = score(ext, ["Technical depth"])
    assert ss.scores[0].score is None  # gate demoted empty-evidence score
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/unit/test_passes.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

`app/pipeline/__init__.py`: empty file.

`app/pipeline/passes.py`:
```python
from typing import Literal
from pydantic import BaseModel

from app.llm import complete_json

class Claim(BaseModel):
    category: Literal["team_size", "tenure", "role_scope", "project_ownership", "metric", "other"]
    statement: str
    value: str = ""

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
    score: int | None = None
    evidence: list[str] = []
    rationale: str = ""

class ScoreSet(BaseModel):
    scores: list[CompetencyScore] = []

class Flag(BaseModel):
    type: Literal["leading_question", "non_job_related", "vague_feedback"]
    excerpt: str = ""
    note: str = ""

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
        if s.score is not None and not s.evidence:
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest tests/unit/test_passes.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/pipeline tests/unit/test_passes.py
git commit -m "feat: extraction, scoring and flag passes with enforced evidence gate"
```

---

### Task 7: Analytics — coverage, disagreement, claim contradictions

**Files:**
- Create: `app/analytics.py`
- Test: `tests/unit/test_analytics.py`

**Interfaces:**
- Consumes: `app.llm.complete_json` (only inside `confirm_contradiction`).
- Produces: `coverage(rows: list[dict]) -> dict[str, list[str]]` — input rows `{"competency", "score", "interviewer"}`; output `{"assessed": [...], "unassessed": [...]}` (insertion-ordered). `disagreements(rows: list[dict]) -> list[dict]` — `{"competency", "spread", "scores": {interviewer: score}}` where max−min ≥ 2. `contradiction_candidates(claims: list[dict]) -> list[tuple[dict, dict]]` — input `{"category", "statement", "value", "interview_id"}`; pairs with same category, different non-empty values, different interviews. `confirm_contradiction(a: dict, b: dict) -> bool` (one LLM call; internal `Verdict(BaseModel)` with field `contradictory: bool`).

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_analytics.py`:
```python
import app.llm as llm
from app.analytics import (
    contradiction_candidates, confirm_contradiction, coverage, disagreements,
)

def test_coverage_splits_assessed_and_unassessed():
    rows = [
        {"competency": "A", "score": 3, "interviewer": "P"},
        {"competency": "B", "score": None, "interviewer": "P"},
        {"competency": "B", "score": 2, "interviewer": "M"},
        {"competency": "C", "score": None, "interviewer": "M"},
    ]
    cov = coverage(rows)
    assert cov["assessed"] == ["A", "B"]
    assert cov["unassessed"] == ["C"]

def test_disagreement_requires_spread_of_two():
    rows = [
        {"competency": "A", "score": 4, "interviewer": "P"},
        {"competency": "A", "score": 2, "interviewer": "M"},
        {"competency": "B", "score": 3, "interviewer": "P"},
        {"competency": "B", "score": 2, "interviewer": "M"},
    ]
    d = disagreements(rows)
    assert len(d) == 1 and d[0]["competency"] == "A" and d[0]["spread"] == 2

def test_contradiction_candidates_same_category_conflicting_values():
    claims = [
        {"category": "team_size", "statement": "led 8", "value": "8", "interview_id": 1},
        {"category": "team_size", "statement": "team of 3", "value": "3", "interview_id": 3},
        {"category": "tenure", "statement": "8 years", "value": "8", "interview_id": 1},
    ]
    pairs = contradiction_candidates(claims)
    assert len(pairs) == 1
    assert {pairs[0][0]["value"], pairs[0][1]["value"]} == {"8", "3"}

def test_confirm_contradiction_uses_llm_verdict(monkeypatch):
    monkeypatch.setattr(llm, "PROVIDERS", [lambda **kw: {"contradictory": True}])
    assert confirm_contradiction({"statement": "led 8"}, {"statement": "team of 3"}) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/unit/test_analytics.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

`app/analytics.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest tests/unit/test_analytics.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/analytics.py tests/unit/test_analytics.py
git commit -m "feat: deterministic coverage, disagreement and claim contradiction analytics"
```

---

### Task 8: Persistence — upsert interview with child rows

**Files:**
- Create: `app/pipeline/persist.py`
- Test: `tests/unit/test_persist.py`

**Interfaces:**
- Consumes: models from Task 4; `Extraction`, `ScoreSet`, `FlagSet` from Task 6; `resolve_rubric` from Task 5.
- Produces: `app.pipeline.persist.save_interview(session, extraction: Extraction, scoreset: ScoreSet, flagset: FlagSet, summary: str, raw_payload: dict, source: str, rubric: list[str]) -> Interview`. Behavior: get-or-create Role (by lowercased title; rubric stored; `dashboard_token` from `settings.dashboard_token`), get-or-create Candidate (name lowercased/stripped), idempotent on `dedup_hash` (existing interview → delete its child rows, rewrite, update summary/raw), writes ScorecardRow/ClaimRow/FlagRow children, commits, returns the Interview.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_persist.py`:
```python
from app.models import Candidate, ClaimRow, Interview, ScorecardRow
from app.pipeline.passes import Claim, CompetencyScore, Extraction, Flag, FlagSet, ScoreSet
from app.pipeline.persist import save_interview

EXT = Extraction(is_interview=True, candidate_name="Aisha Verma", role_title="Backend Engineer",
                 interviewer="Priya", exchanges=[],
                 claims=[Claim(category="team_size", statement="led a team of 8", value="8")])
SS = ScoreSet(scores=[CompetencyScore(competency="Technical depth", score=3, evidence=["q"], rationale="r")])
FS = FlagSet(flags=[Flag(type="vague_feedback", excerpt="vibes", note="n")])

def test_save_creates_role_candidate_interview_and_children(session):
    iv = save_interview(session, EXT, SS, FS, "summary", {"raw": 1}, "test", ["Technical depth"])
    assert iv.id is not None
    assert session.query(Candidate).one().name == "aisha verma"
    assert session.query(ScorecardRow).count() == 1
    assert session.query(ClaimRow).one().value == "8"

def test_save_is_idempotent_on_same_summary(session):
    save_interview(session, EXT, SS, FS, "summary", {}, "test", ["Technical depth"])
    save_interview(session, EXT, SS, FS, "summary", {}, "test", ["Technical depth"])
    assert session.query(Interview).count() == 1
    assert session.query(ScorecardRow).count() == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/unit/test_persist.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

`app/pipeline/persist.py`:
```python
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

def save_interview(session: Session, extraction: Extraction, scoreset: ScoreSet, flagset: FlagSet,
                   summary: str, raw_payload: dict, source: str, rubric: list[str]) -> Interview:
    role = _get_or_create_role(session, extraction.role_title, rubric)
    cand = _get_or_create_candidate(session, extraction.candidate_name, role.id)
    h = dedup_hash(extraction.candidate_name, extraction.interviewer, summary)
    iv = session.query(Interview).filter(Interview.dedup_hash == h).one_or_none()
    if iv is None:
        iv = Interview(candidate_id=cand.id, interviewer=extraction.interviewer, summary=summary,
                       raw_payload=raw_payload, source=source, dedup_hash=h)
        session.add(iv)
        session.flush()
    else:
        for model in (ScorecardRow, ClaimRow, FlagRow):
            session.query(model).filter(model.interview_id == iv.id).delete()
        iv.summary, iv.raw_payload, iv.source = summary, raw_payload, source
    for s in scoreset.scores:
        session.add(ScorecardRow(interview_id=iv.id, competency=s.competency, score=s.score,
                                 evidence=s.evidence, rationale=s.rationale))
    for c in extraction.claims:
        session.add(ClaimRow(candidate_id=cand.id, interview_id=iv.id, category=c.category,
                             statement=c.statement, value=c.value))
    for f in flagset.flags:
        session.add(FlagRow(interview_id=iv.id, type=f.type, excerpt=f.excerpt, note=f.note))
    session.commit()
    return iv
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest tests/unit/test_persist.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/persist.py tests/unit/test_persist.py
git commit -m "feat: idempotent interview persistence with role and candidate upserts"
```

---

### Task 9: Artifact composition + panel snapshot queries

**Files:**
- Create: `app/pipeline/artifact.py`
- Test: `tests/unit/test_artifact.py`

**Interfaces:**
- Consumes: models, `analytics.coverage/disagreements/contradiction_candidates/confirm_contradiction`, `settings.base_url`, `settings.dashboard_token`.
- Produces: `app.pipeline.artifact.panel_snapshot(session, interview) -> dict` with keys `coverage: dict`, `disagreements: list`, `contradictions: list[dict]` (each `{"a": statement, "b": statement, "categories": str}`; only LLM-confirmed pairs); `app.pipeline.artifact.compose_markdown(interview, scoreset, flagset, snapshot) -> str` (scorecard table, flags section, panel snapshot section, dashboard link `{base_url}/d/{token}`); `app.pipeline.artifact.SCORE_LABELS = {1: "Weak", 2: "Developing", 3: "Solid", 4: "Exceptional"}`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_artifact.py`:
```python
import app.llm as llm
from app.pipeline.artifact import compose_markdown, panel_snapshot
from app.pipeline.passes import (Claim, CompetencyScore, Extraction, Flag, FlagSet, ScoreSet)
from app.pipeline.persist import save_interview

def _seed(session, name, interviewer, summary, claims, scores):
    ext = Extraction(is_interview=True, candidate_name=name, role_title="Backend Engineer",
                     interviewer=interviewer, exchanges=[], claims=claims)
    ss = ScoreSet(scores=scores)
    return save_interview(session, ext, ss, FlagSet(), summary, {}, "test", ["Technical depth", "System design"])

def test_snapshot_reports_gap_and_confirmed_contradiction(session, monkeypatch):
    monkeypatch.setattr(llm, "PROVIDERS", [lambda **kw: {"contradictory": True}])
    _seed(session, "Aisha", "Priya", "s1",
          [Claim(category="team_size", statement="led a team of 8", value="8")],
          [CompetencyScore(competency="Technical depth", score=4, evidence=["e"], rationale="")])
    iv = _seed(session, "Aisha", "Sam", "s2",
               [Claim(category="team_size", statement="we were 3", value="3")],
               [CompetencyScore(competency="Technical depth", score=2, evidence=["e"], rationale="")])
    snap = panel_snapshot(session, iv)
    assert "System design" in snap["coverage"]["unassessed"]
    assert snap["disagreements"][0]["spread"] == 2
    assert len(snap["contradictions"]) == 1

def test_compose_markdown_contains_key_sections(session):
    iv = _seed(session, "Aisha", "Priya", "s1", [],
               [CompetencyScore(competency="Technical depth", score=3, evidence=["quote"], rationale="r")])
    ss = ScoreSet(scores=[CompetencyScore(competency="Technical depth", score=3, evidence=["quote"], rationale="r")])
    md = compose_markdown(iv, ss, FlagSet(flags=[Flag(type="non_job_related", excerpt="x", note="n")]),
                          {"coverage": {"assessed": ["Technical depth"], "unassessed": ["System design"]},
                           "disagreements": [], "contradictions": []})
    assert "Technical depth" in md and "Solid" in md
    assert "System design" in md            # gap listed
    assert "non_job_related" in md or "Non-job-related" in md
    assert "/d/" in md                       # dashboard link
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/unit/test_artifact.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

`app/pipeline/artifact.py`:
```python
from sqlalchemy.orm import Session

from app.analytics import confirm_contradiction, contradiction_candidates, coverage, disagreements
from app.config import settings
from app.models import Candidate, ClaimRow, Interview, ScorecardRow
from app.pipeline.passes import FlagSet, ScoreSet

SCORE_LABELS = {1: "Weak", 2: "Developing", 3: "Solid", 4: "Exceptional"}

_FLAG_TITLES = {"leading_question": "Leading question", "non_job_related": "Non-job-related topic",
                "vague_feedback": "Vague feedback"}

def panel_snapshot(session: Session, interview: Interview) -> dict:
    cand = session.get(Candidate, interview.candidate_id)
    ivs = session.query(Interview).filter(Interview.candidate_id == cand.id).all()
    iv_by_id = {iv.id: iv for iv in ivs}
    rows = [
        {"competency": r.competency, "score": r.score, "interviewer": iv_by_id[r.interview_id].interviewer}
        for r in session.query(ScorecardRow).filter(ScorecardRow.interview_id.in_(iv_by_id)).all()
    ]
    claims = [
        {"category": c.category, "statement": c.statement, "value": c.value, "interview_id": c.interview_id}
        for c in session.query(ClaimRow).filter(ClaimRow.candidate_id == cand.id).all()
    ]
    contradictions = [
        {"a": a["statement"], "b": b["statement"], "categories": a["category"]}
        for a, b in contradiction_candidates(claims)
        if confirm_contradiction(a, b)
    ]
    return {"coverage": coverage(rows), "disagreements": disagreements(rows), "contradictions": contradictions}

def compose_markdown(interview: Interview, scoreset: ScoreSet, flagset: FlagSet, snapshot: dict) -> str:
    lines = [f"## Interview Scorecard — {interview.interviewer or 'interview'}", "",
             "| Competency | Score | Evidence |", "|---|---|---|"]
    for s in scoreset.scores:
        label = f"{s.score} — {SCORE_LABELS[s.score]}" if s.score else "Not assessed"
        ev = "; ".join(s.evidence) if s.evidence else s.rationale or "—"
        lines.append(f"| {s.competency} | {label} | {ev} |")
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest tests/unit/test_artifact.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/artifact.py tests/unit/test_artifact.py
git commit -m "feat: panel snapshot queries and markdown artifact composition"
```

---

### Task 10: Pipeline orchestrator + real /run and /test

**Files:**
- Create: `app/pipeline/__init__.py` (replace empty file)
- Modify: `app/main.py`
- Test: `tests/integration/test_run_flow.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `app.pipeline.run_pipeline(normalized: NormalizedTask, source: str, session: Session) -> dict` (SitRep artifacts envelope). Behaviors: non-interview → polite artifact; `LLMUnavailable` → graceful artifact; success → scorecard artifact. `app/main.py` gains startup DB binding and per-request sessions; `/run`,`/test` call `run_pipeline`.

- [ ] **Step 1: Write the failing tests**

`tests/integration/test_run_flow.py`:
```python
from fastapi.testclient import TestClient

import app.llm as llm
import app.main as main_mod
from app.main import app
from app.pipeline.passes import Extraction

PAYLOAD = {"task": {"title": "Interview debrief", "description": ""},
           "summary": "Priya interviewed Aisha Verma for Backend Engineer. Aisha said she led a team of 8. "
                      "She explained a sharding migration in depth.",
           "attendees": ["Priya", "Aisha Verma"]}

def fake_llm(**kw):
    if kw["schema"] is Extraction:
        return {"is_interview": True, "candidate_name": "Aisha Verma", "role_title": "Backend Engineer",
                "interviewer": "Priya",
                "exchanges": [{"question": "sharding?", "answer_summary": "explained migration in depth"}],
                "claims": [{"category": "team_size", "statement": "led a team of 8", "value": "8"}]}
    name = kw["schema"].__name__
    if name == "ScoreSet":
        return {"scores": [{"competency": "Technical depth", "score": 4,
                            "evidence": ["explained a sharding migration in depth"], "rationale": "strong"}]}
    if name == "FlagSet":
        return {"flags": []}
    return {"contradictory": False}

def test_run_produces_scorecard_artifact(client_with_db, monkeypatch):
    monkeypatch.setattr(llm, "PROVIDERS", [fake_llm])
    resp = client_with_db.post("/run", json=PAYLOAD)
    assert resp.status_code == 200
    content = resp.json()["artifacts"][0]["content"]
    assert "Technical depth" in content and "Exceptional" in content

def test_non_interview_gets_polite_artifact(client_with_db, monkeypatch):
    def not_interview(**kw):
        if kw["schema"] is Extraction:
            return {"is_interview": False}
        raise AssertionError("should not score a non-interview")
    monkeypatch.setattr(llm, "PROVIDERS", [not_interview])
    resp = client_with_db.post("/run", json={"task": {"title": "Sprint sync"}, "summary": "We planned the sprint."})
    assert resp.status_code == 200
    assert "doesn't look like an interview" in resp.json()["artifacts"][0]["content"]

def test_llm_down_returns_graceful_artifact_not_500(client_with_db, monkeypatch):
    def boom(**kw):
        raise RuntimeError("both providers down")
    monkeypatch.setattr(llm, "PROVIDERS", [boom])
    monkeypatch.setattr(llm, "RETRY_SLEEP", 0)
    resp = client_with_db.post("/run", json=PAYLOAD)
    assert resp.status_code == 200
    assert "couldn't analyze" in resp.json()["artifacts"][0]["content"]
```

Add to `tests/conftest.py`:
```python
from fastapi.testclient import TestClient
from app.db import SessionLocal

@pytest.fixture()
def client_with_db(session):
    # bind the app's session factory to the test's in-memory engine
    SessionLocal.configure(bind=session.get_bind())
    from app.main import app
    return TestClient(app)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/integration/test_run_flow.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

`app/pipeline/__init__.py`:
```python
import logging

from sqlalchemy.orm import Session

from app.llm import LLMUnavailable
from app.pipeline import passes
from app.pipeline.artifact import compose_markdown, panel_snapshot
from app.pipeline.persist import save_interview
from app.rubrics import resolve_rubric
from app.sitrep import NormalizedTask, artifact_response

logger = logging.getLogger("pipeline")

def run_pipeline(normalized: NormalizedTask, source: str, session: Session) -> dict:
    try:
        extraction = passes.extract(normalized.summary, normalized.title,
                                    normalized.description, normalized.attendees)
        if not extraction.is_interview:
            return artifact_response(
                "Interview Scorecard",
                "This meeting doesn't look like an interview, so no scorecard was generated. "
                "Interview Scorecard runs on interview debrief tasks.")
        rubric = resolve_rubric(extraction.role_title, normalized.instructions)
        scoreset = passes.score(extraction, rubric)
        flagset = passes.detect_flags(normalized.summary)
        interview = save_interview(session, extraction, scoreset, flagset,
                                   normalized.summary, normalized.raw, source, rubric)
        snapshot = panel_snapshot(session, interview)
        return artifact_response(f"Scorecard: {extraction.candidate_name.title()}",
                                 compose_markdown(interview, scoreset, flagset, snapshot))
    except LLMUnavailable as e:
        logger.error("llm unavailable: %s", e)
        return artifact_response(
            "Interview Scorecard",
            "We couldn't analyze this meeting right now (AI providers unavailable). "
            "Your meeting data is safe — re-run this task in a few minutes.")

```

Replace `app/main.py` with:
```python
import json
import logging

from fastapi import FastAPI, Request

from app.db import SessionLocal, bind_default_engine
from app.pipeline import run_pipeline
from app.sitrep import parse_sitrep_request

logger = logging.getLogger("sitrep")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Interview Scorecard")

@app.on_event("startup")
def _startup():
    bind_default_engine()

@app.get("/healthz")
def healthz():
    return {"ok": True}

async def _handle(request: Request, source: str) -> dict:
    payload = await request.json()
    logger.info("WIRE_CAPTURE %s %s", source, json.dumps(payload)[:4000])
    normalized = parse_sitrep_request(payload)
    session = SessionLocal()
    try:
        return run_pipeline(normalized, source, session)
    finally:
        session.close()

@app.post("/run")
async def run(request: Request):
    return await _handle(request, "run")

@app.post("/test")
async def test(request: Request):
    return await _handle(request, "test")
```

- [ ] **Step 4: Run the whole suite**

Run: `.venv\Scripts\pytest -v`
Expected: ALL PASS (integration + all prior unit tests; `client_with_db` keeps `/test` stub test working — if `tests/integration/test_endpoints_stub.py` now fails because endpoints run the real pipeline, update it to monkeypatch `llm.PROVIDERS` with the `not_interview` fake and assert 200 + artifacts envelope, or delete it as superseded by `test_run_flow.py`).

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/__init__.py app/main.py tests
git commit -m "feat: full pipeline orchestration behind run and test endpoints"
```

---

### Task 11: Dashboard — three pages

**Files:**
- Create: `app/web/__init__.py` (empty), `app/web/routes.py`, `app/web/templates/base.html`, `app/web/templates/home.html`, `app/web/templates/matrix.html`, `app/web/templates/candidate.html`
- Modify: `app/main.py` (include router)
- Test: `tests/integration/test_dashboard.py`

**Interfaces:**
- Consumes: models, analytics, `settings.dashboard_token`.
- Produces: `GET /d/{token}` (home), `GET /d/{token}/role/{role_id}` (matrix), `GET /d/{token}/candidate/{candidate_id}` (detail); wrong token → 404. Router exported as `app.web.routes.router`.

**Design notes (apply, don't reinterpret):** dark theme (`bg-zinc-950` base, zinc-100 text, emerald/amber/red score accents), Tailwind + Alpine via CDN in `base.html`, filled-dot score scale (●●●○), gray hatch “Not assessed”, ⚠/◐ badges on candidate columns, Alpine `x-show` slide-over panel on cell click fed by JSON embedded via `<script type="application/json">`. Every page renders sensibly with 1 candidate / 1 interview (empty-state copy: "Panel in progress — n of N perspectives").

- [ ] **Step 1: Write the failing tests**

`tests/integration/test_dashboard.py`:
```python
from app.config import settings
from app.pipeline.passes import Claim, CompetencyScore, Extraction, FlagSet, ScoreSet
from app.pipeline.persist import save_interview

def _seed(session):
    ext = Extraction(is_interview=True, candidate_name="Aisha Verma", role_title="Backend Engineer",
                     interviewer="Priya", exchanges=[],
                     claims=[Claim(category="team_size", statement="led 8", value="8")])
    ss = ScoreSet(scores=[CompetencyScore(competency="Technical depth", score=4, evidence=["e"], rationale="r")])
    return save_interview(session, ext, ss, FlagSet(), "s", {}, "test", ["Technical depth", "System design"])

def test_home_lists_roles_and_wrong_token_404(client_with_db, session):
    _seed(session)
    ok = client_with_db.get(f"/d/{settings.dashboard_token}")
    assert ok.status_code == 200 and "backend engineer" in ok.text.lower()
    assert client_with_db.get("/d/wrong-token").status_code == 404

def test_matrix_shows_candidate_and_not_assessed(client_with_db, session):
    iv = _seed(session)
    resp = client_with_db.get(f"/d/{settings.dashboard_token}/role/1")
    assert resp.status_code == 200
    assert "aisha verma" in resp.text.lower()
    assert "Not assessed" in resp.text          # System design has no scores

def test_candidate_page_shows_timeline(client_with_db, session):
    _seed(session)
    resp = client_with_db.get(f"/d/{settings.dashboard_token}/candidate/1")
    assert resp.status_code == 200 and "Priya" in resp.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/integration/test_dashboard.py -v`
Expected: FAIL (404 everywhere).

- [ ] **Step 3: Implement routes**

`app/web/routes.py`:
```python
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.analytics import coverage, disagreements
from app.config import settings
from app.db import SessionLocal
from app.models import Candidate, ClaimRow, FlagRow, Interview, Role, ScorecardRow

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

def _check(token: str):
    if token != settings.dashboard_token:
        raise HTTPException(status_code=404)

def _score_rows(session, candidate_ids):
    ivs = session.query(Interview).filter(Interview.candidate_id.in_(candidate_ids)).all()
    iv_by_id = {iv.id: iv for iv in ivs}
    rows = session.query(ScorecardRow).filter(ScorecardRow.interview_id.in_(iv_by_id)).all()
    return ivs, iv_by_id, rows

@router.get("/d/{token}")
def home(token: str, request: Request):
    _check(token)
    session = SessionLocal()
    try:
        roles = session.query(Role).all()
        cards = []
        for role in roles:
            cands = session.query(Candidate).filter(Candidate.role_id == role.id).all()
            n_iv = session.query(Interview).filter(
                Interview.candidate_id.in_([c.id for c in cands] or [0])).count()
            cards.append({"role": role, "candidates": len(cands), "interviews": n_iv})
        return templates.TemplateResponse(request, "home.html", {"cards": cards, "token": token})
    finally:
        session.close()

@router.get("/d/{token}/role/{role_id}")
def matrix(token: str, role_id: int, request: Request):
    _check(token)
    session = SessionLocal()
    try:
        role = session.get(Role, role_id) or _404()
        rubric = role.rubric["competencies"]
        cands = session.query(Candidate).filter(Candidate.role_id == role.id).all()
        columns = []
        for cand in cands:
            ivs, iv_by_id, rows = _score_rows(session, [cand.id])
            per_comp = defaultdict(list)
            detail = defaultdict(list)
            for r in rows:
                if r.score is not None:
                    per_comp[r.competency].append(r.score)
                detail[r.competency].append({
                    "interviewer": iv_by_id[r.interview_id].interviewer,
                    "score": r.score, "evidence": r.evidence, "rationale": r.rationale})
            cells = []
            for comp in rubric:
                scores = per_comp.get(comp, [])
                cells.append({"competency": comp,
                              "avg": round(sum(scores) / len(scores), 1) if scores else None,
                              "detail": detail.get(comp, [])})
            cov = coverage([{"competency": r.competency, "score": r.score,
                             "interviewer": iv_by_id[r.interview_id].interviewer} for r in rows])
            claims = session.query(ClaimRow).filter(ClaimRow.candidate_id == cand.id).all()
            vals = defaultdict(set)
            for c in claims:
                if c.value:
                    vals[c.category].add(c.value)
            columns.append({"candidate": cand, "cells": cells,
                            "gap": bool(set(rubric) - set(cov["assessed"])),
                            "conflict": any(len(v) > 1 for v in vals.values()),
                            "n_interviews": len(ivs)})
        return templates.TemplateResponse(request, "matrix.html",
            {"role": role, "rubric": rubric, "columns": columns, "token": token})
    finally:
        session.close()

@router.get("/d/{token}/candidate/{candidate_id}")
def candidate(token: str, candidate_id: int, request: Request):
    _check(token)
    session = SessionLocal()
    try:
        cand = session.get(Candidate, candidate_id) or _404()
        ivs, iv_by_id, rows = _score_rows(session, [cand.id])
        by_iv = defaultdict(list)
        for r in rows:
            by_iv[r.interview_id].append(r)
        flags = session.query(FlagRow).filter(FlagRow.interview_id.in_(iv_by_id or [0])).all()
        claims = session.query(ClaimRow).filter(ClaimRow.candidate_id == cand.id).all()
        score_rows = [{"competency": r.competency, "score": r.score,
                       "interviewer": iv_by_id[r.interview_id].interviewer} for r in rows]
        return templates.TemplateResponse(request, "candidate.html",
            {"cand": cand, "interviews": ivs, "by_iv": by_iv, "flags": flags, "claims": claims,
             "coverage": coverage(score_rows), "disagreements": disagreements(score_rows), "token": token})
    finally:
        session.close()

def _404():
    raise HTTPException(status_code=404)
```

Add to `app/main.py` after `app = FastAPI(...)`:
```python
from app.web.routes import router as dashboard_router
app.include_router(dashboard_router)
```

- [ ] **Step 4: Implement templates**

`app/web/templates/base.html`:
```html
<!doctype html>
<html class="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Interview Scorecard{% endblock %}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3/dist/cdn.min.js"></script>
</head>
<body class="bg-zinc-950 text-zinc-100 min-h-screen font-sans antialiased">
  <header class="border-b border-zinc-800 px-6 py-4 flex items-center gap-3">
    <span class="text-emerald-400 text-xl">▣</span>
    <a href="/d/{{ token }}" class="font-semibold tracking-tight">Interview Scorecard</a>
    <span class="text-zinc-500 text-sm">panel intelligence</span>
  </header>
  <main class="max-w-6xl mx-auto px-6 py-8">{% block content %}{% endblock %}</main>
</body>
</html>
```

`app/web/templates/home.html`:
```html
{% extends "base.html" %}
{% block content %}
<h1 class="text-2xl font-semibold mb-6">Hiring pipeline</h1>
{% if not cards %}<p class="text-zinc-400">No interviews analyzed yet. Run the agent on an interview meeting in SitRep.</p>{% endif %}
<div class="grid md:grid-cols-2 gap-4">
  {% for c in cards %}
  <a href="/d/{{ token }}/role/{{ c.role.id }}"
     class="block rounded-xl border border-zinc-800 bg-zinc-900/60 p-5 hover:border-emerald-500/50 transition">
    <div class="text-lg font-medium capitalize">{{ c.role.title }}</div>
    <div class="text-sm text-zinc-400 mt-1">{{ c.candidates }} candidate(s) · {{ c.interviews }} interview(s)</div>
  </a>
  {% endfor %}
</div>
{% endblock %}
```

`app/web/templates/matrix.html`:
```html
{% extends "base.html" %}
{% block title %}{{ role.title|title }} — matrix{% endblock %}
{% block content %}
<div x-data="{open:null}">
<h1 class="text-2xl font-semibold capitalize">{{ role.title }} — comparison matrix</h1>
<p class="text-zinc-400 text-sm mt-1 mb-6">Click any cell for per-interviewer evidence.</p>
<div class="overflow-x-auto rounded-xl border border-zinc-800">
<table class="w-full text-sm">
  <thead class="bg-zinc-900">
    <tr>
      <th class="text-left px-4 py-3 text-zinc-400 font-medium">Competency</th>
      {% for col in columns %}
      <th class="px-4 py-3 text-left">
        <a href="/d/{{ token }}/candidate/{{ col.candidate.id }}" class="capitalize font-medium hover:text-emerald-400">{{ col.candidate.name }}</a>
        <span class="ml-1">
          {% if col.conflict %}<span title="claim inconsistency" class="text-red-400">⚠</span>{% endif %}
          {% if col.gap %}<span title="coverage incomplete" class="text-amber-400">◐</span>{% endif %}
        </span>
        <div class="text-xs text-zinc-500 font-normal">{{ col.n_interviews }} interview(s)</div>
      </th>
      {% endfor %}
    </tr>
  </thead>
  <tbody>
    {% for comp in rubric %}
    <tr class="border-t border-zinc-800/70">
      <td class="px-4 py-3 text-zinc-300">{{ comp }}</td>
      {% for col in columns %}
      {% for cell in col.cells %}{% if cell.competency == comp %}
      <td class="px-4 py-3 cursor-pointer hover:bg-zinc-900/80"
          @click="open = {cand: '{{ col.candidate.name }}', comp: '{{ comp }}', detail: {{ cell.detail|tojson }}}">
        {% if cell.avg %}
          {% set full = cell.avg|round(0, 'floor')|int %}
          <span class="{% if cell.avg >= 3.5 %}text-emerald-400{% elif cell.avg >= 2.5 %}text-emerald-300{% elif cell.avg >= 1.5 %}text-amber-400{% else %}text-red-400{% endif %} tracking-widest">
            {%- for i in range(4) %}{{ '●' if i < full else '○' }}{% endfor -%}
          </span>
          <span class="ml-2 text-zinc-400">{{ cell.avg }}</span>
        {% else %}
          <span class="text-zinc-600 italic">Not assessed</span>
        {% endif %}
      </td>
      {% endif %}{% endfor %}
      {% endfor %}
    </tr>
    {% endfor %}
  </tbody>
</table>
</div>

<!-- slide-over -->
<div x-cloak x-show="open" @click.self="open=null"
     class="fixed inset-0 bg-black/60 flex justify-end z-50">
  <div class="w-full max-w-md bg-zinc-900 border-l border-zinc-700 p-6 overflow-y-auto">
    <button @click="open=null" class="text-zinc-500 hover:text-zinc-200 float-right">✕</button>
    <h2 class="text-lg font-semibold capitalize" x-text="open?.cand"></h2>
    <p class="text-sm text-emerald-400 mb-4" x-text="open?.comp"></p>
    <template x-for="d in (open?.detail || [])">
      <div class="mb-4 rounded-lg border border-zinc-800 p-4">
        <div class="flex justify-between text-sm">
          <span class="font-medium" x-text="d.interviewer || 'interviewer'"></span>
          <span x-text="d.score ? d.score + ' / 4' : 'Not assessed'"
                :class="d.score ? 'text-emerald-400' : 'text-zinc-500'"></span>
        </div>
        <template x-for="e in (d.evidence || [])">
          <blockquote class="mt-2 text-sm text-zinc-300 border-l-2 border-emerald-500/50 pl-3" x-text="e"></blockquote>
        </template>
        <p class="mt-2 text-xs text-zinc-500" x-text="d.rationale"></p>
      </div>
    </template>
  </div>
</div>
</div>
{% endblock %}
```

`app/web/templates/candidate.html`:
```html
{% extends "base.html" %}
{% block title %}{{ cand.name|title }}{% endblock %}
{% block content %}
<h1 class="text-2xl font-semibold capitalize">{{ cand.name }}</h1>
<p class="text-zinc-400 text-sm mt-1 mb-6">{{ interviews|length }} interview(s)</p>

{% if coverage.unassessed %}
<div class="mb-4 rounded-lg border border-amber-500/40 bg-amber-500/5 px-4 py-3 text-sm">
  ◐ Still unprobed: <span class="text-amber-300">{{ coverage.unassessed|join(", ") }}</span>
  — brief the next interviewer to cover these.
</div>
{% endif %}
{% for d in disagreements %}
<div class="mb-4 rounded-lg border border-red-500/40 bg-red-500/5 px-4 py-3 text-sm">
  ⚡ Panel disagrees on <b>{{ d.competency }}</b> (spread {{ d.spread }}):
  {% for k, v in d.scores.items() %}{{ k }}: {{ v }}{{ ", " if not loop.last }}{% endfor %}
</div>
{% endfor %}
{% if claims %}
<h2 class="text-lg font-medium mt-8 mb-3">Claim ledger</h2>
<div class="rounded-xl border border-zinc-800 divide-y divide-zinc-800/70 text-sm">
  {% for c in claims %}
  <div class="px-4 py-3 flex gap-3">
    <span class="text-zinc-500 w-36 shrink-0">{{ c.category|replace("_", " ") }}</span>
    <span>“{{ c.statement }}”</span>
    <span class="ml-auto text-zinc-400">{{ c.value }}</span>
  </div>
  {% endfor %}
</div>
{% endif %}

<h2 class="text-lg font-medium mt-8 mb-3">Interviews</h2>
{% for iv in interviews %}
<div class="mb-4 rounded-xl border border-zinc-800 bg-zinc-900/50 p-5">
  <div class="flex justify-between text-sm mb-3">
    <span class="font-medium">{{ iv.interviewer or "Interview" }}</span>
    <span class="text-zinc-500">{{ iv.meeting_date.strftime("%b %d, %Y") }}</span>
  </div>
  <table class="w-full text-sm">
    {% for r in by_iv[iv.id] %}
    <tr class="border-t border-zinc-800/60">
      <td class="py-2 text-zinc-300">{{ r.competency }}</td>
      <td class="py-2 w-28">{% if r.score %}<span class="text-emerald-400">{{ r.score }} / 4</span>
          {% else %}<span class="text-zinc-600 italic">Not assessed</span>{% endif %}</td>
      <td class="py-2 text-zinc-400">{{ r.evidence|join("; ") if r.evidence else r.rationale }}</td>
    </tr>
    {% endfor %}
  </table>
</div>
{% endfor %}
{% for f in flags %}
<div class="mb-2 rounded-lg border border-red-500/30 bg-red-500/5 px-4 py-2 text-sm">
  ⚠ <b>{{ f.type|replace("_", " ") }}</b>: “{{ f.excerpt }}” — {{ f.note }}
</div>
{% endfor %}
{% endblock %}
```

Jinja note: the matrix cell is selected with an if-guarded inner loop (`{% for cell in col.cells %}{% if cell.competency == comp %}`) because Jinja has no `break`; each competency appears exactly once per column, so exactly one cell renders.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\pytest tests/integration/test_dashboard.py -v`
Expected: PASS (3 tests). Then run the full suite: `.venv\Scripts\pytest -q` — ALL PASS.

- [ ] **Step 6: Visual check**

Run: `.venv\Scripts\uvicorn app.main:app --port 8000`, open `http://localhost:8000/d/dev-token` after seeding (Task 12) or with existing local data. Verify dark theme, matrix dots, slide-over.

- [ ] **Step 7: Commit**

```bash
git add app/web app/main.py tests/integration/test_dashboard.py
git commit -m "feat: dashboard with pipeline home, comparison matrix and candidate detail"
```

---

### Task 12: Demo fixtures + seed script

**Files:**
- Create: `fixtures/interviews/a1_priya_technical.json`, `a2_marco_systemdesign.json`, `a3_sam_behavioral.json`, `b1_priya_technical.json`, `b2_sam_behavioral.json`, `scripts/seed.py`
- Test: covered by running the seed against a live local instance.

**Interfaces:**
- Consumes: `POST /test` wire format (as corrected in Task 3 Step 8 — adjust fixture key names to the captured format).
- Produces: 5 payload files + `scripts/seed.py` that POSTs each to `{BASE}/test`.

**Planted demo beats:** A3 contradicts A1 on team size (8 vs 3); A3 contains a non-job-related question (family plans) and vague "culture fit" feedback; System design is probed only by Marco (A2) so candidate B shows a ◐ coverage gap; B scores lower than A on Technical depth so the matrix shows contrast.

- [ ] **Step 1: Write the fixtures**

`fixtures/interviews/a1_priya_technical.json`:
```json
{
  "task": {"title": "Interview debrief: Aisha Verma", "description": "Technical interview for Backend Engineer"},
  "attendees": ["Priya Nair", "Aisha Verma"],
  "summary": "Priya Nair conducted a technical interview with Aisha Verma for the Backend Engineer role. Priya asked Aisha to walk through the hardest scaling problem she has solved. Aisha described leading a team of 8 engineers through a Postgres sharding migration at Finlo, explaining shard-key selection, dual-write cutover, and how they kept p99 latency under 40ms during the transition. Priya then asked how she debugs production incidents; Aisha described a structured approach using distributed tracing and error budgets, citing a specific incident where she isolated a connection-pool leak within an hour. Aisha communicated clearly, used precise terminology, and checked whether her answers matched the question's intent."
}
```

`fixtures/interviews/a2_marco_systemdesign.json`:
```json
{
  "task": {"title": "Interview debrief: Aisha Verma", "description": "System design interview for Backend Engineer"},
  "attendees": ["Marco Ruiz", "Aisha Verma"],
  "summary": "Marco Ruiz ran a system design interview with Aisha Verma for the Backend Engineer position. Marco asked Aisha to design a rate limiter for a multi-tenant API. Aisha proposed a sliding-window counter in Redis with per-tenant quotas, discussed hot-key mitigation, and compared consistency trade-offs between local token buckets and centralized counters. When Marco pushed on failure modes, Aisha explained graceful degradation to a fail-open mode with alerting. She asked clarifying questions about tenant count and traffic shape before committing to a design. Marco noted she structured the whiteboard clearly and adjusted quickly when constraints changed."
}
```

`fixtures/interviews/a3_sam_behavioral.json`:
```json
{
  "task": {"title": "Interview debrief: Aisha Verma", "description": "Behavioral interview for Backend Engineer"},
  "attendees": ["Sam Kowalski", "Aisha Verma"],
  "summary": "Sam Kowalski held a behavioral interview with Aisha Verma for Backend Engineer. Sam asked about a conflict with a colleague; Aisha described disagreeing with a staff engineer about migration sequencing at Finlo, where she said the team was just 3 people including herself and she was the senior-most, so she owned the final call after presenting benchmarks. Sam asked whether she plans to start a family soon, saying the team has a heavy on-call load. Sam wrapped up saying Aisha seems like a great culture fit and he had good vibes overall, and asked wouldn't she agree the team's approach to on-call is best-in-class."
}
```

`fixtures/interviews/b1_priya_technical.json`:
```json
{
  "task": {"title": "Interview debrief: Daniel Okafor", "description": "Technical interview for Backend Engineer"},
  "attendees": ["Priya Nair", "Daniel Okafor"],
  "summary": "Priya Nair interviewed Daniel Okafor for the Backend Engineer role. Priya asked about his most complex backend work. Daniel described maintaining a Django monolith and adding a Celery-based export pipeline; he explained the queue topology but was vague on how he measured throughput, saying it 'felt fast enough'. Asked to debug a hypothetical N+1 query, Daniel identified the problem but needed prompting to reach select_related. He mentioned four years of backend experience at two startups. He answered politely and asked thoughtful questions about the team's code review culture."
}
```

`fixtures/interviews/b2_sam_behavioral.json`:
```json
{
  "task": {"title": "Interview debrief: Daniel Okafor", "description": "Behavioral interview for Backend Engineer"},
  "attendees": ["Sam Kowalski", "Daniel Okafor"],
  "summary": "Sam Kowalski ran a behavioral interview with Daniel Okafor for Backend Engineer. Daniel described taking ownership of a failing release: he coordinated a rollback, wrote the postmortem, and set up a release checklist that cut failed deploys by half over the next quarter. Asked about mentoring, he described onboarding two junior engineers with pairing sessions and written guides. Daniel communicated in an organized, reflective way and gave concrete examples with measurable outcomes."
}
```

- [ ] **Step 2: Write the seed script**

`scripts/seed.py`:
```python
"""POST every fixture to a running instance's /test endpoint, in order."""
import json
import pathlib
import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
FIXTURES = sorted(pathlib.Path(__file__).parent.parent.joinpath("fixtures/interviews").glob("*.json"))

for path in FIXTURES:
    payload = json.loads(path.read_text(encoding="utf-8"))
    resp = httpx.post(f"{BASE}/test", json=payload, timeout=120)
    resp.raise_for_status()
    title = resp.json()["artifacts"][0]["title"]
    print(f"{path.name}: {resp.status_code} -> {title}")
```

- [ ] **Step 3: Run the seed against a live local instance (real LLM keys in .env)**

Run (terminal 1): `.venv\Scripts\uvicorn app.main:app --port 8000`
Run (terminal 2): `.venv\Scripts\python scripts/seed.py`
Expected: five lines ending in `-> Scorecard: Aisha Verma` / `-> Scorecard: Daniel Okafor`.

- [ ] **Step 4: Verify demo beats on the dashboard**

Open `http://localhost:8000/d/dev-token`. Check: matrix shows both candidates; Aisha's column has ⚠ (team-size contradiction 8 vs 3); Daniel's column has ◐ (System design unprobed); candidate page for Aisha shows the non_job_related flag from Sam's interview. If the LLM missed a planted beat, tune the relevant prompt in `app/pipeline/passes.py` (not the fixture) and re-seed.

- [ ] **Step 5: Commit**

```bash
git add fixtures scripts/seed.py
git commit -m "feat: demo fixtures with planted contradiction, gap and compliance flag"
```

---

### Task 13: Deploy, publish, submission assets

**Files:**
- Create: `render.yaml`, `LICENSE`, `README.md`
- Modify: `.env` values on Render dashboard (not in repo)

**Interfaces:**
- Consumes: the whole app.
- Produces: live Render URL wired into the SitRep Studio draft; published marketplace agent; public GitHub repo.

- [ ] **Step 1: Write render.yaml**

```yaml
services:
  - type: web
    name: interview-scorecard
    runtime: python
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: GEMINI_API_KEY
        sync: false
      - key: GROQ_API_KEY
        sync: false
      - key: DATABASE_URL
        sync: false
      - key: DASHBOARD_TOKEN
        sync: false
      - key: BASE_URL
        sync: false
```

- [ ] **Step 2: Write LICENSE (MIT, current year, Ruhan Wankhede) and README.md**

README must contain: what it does (3 bullets + screenshot), architecture diagram (mermaid: SitRep → /run → extract/score/flags → Neon → artifact + dashboard), local setup (venv, .env from .env.example, uvicorn, seed script), deployment (Render + Neon + UptimeRobot steps), SitRep configuration (endpoint URL, Summary trigger, `competencies:` override syntax), test instructions (`pytest`), free-tier notes (models used, fallback chain).

- [ ] **Step 3: Deploy**

Push repo to GitHub (public). On render.com: New → Blueprint → select repo. Set the five env vars (Neon connection string from neon.tech dashboard; generate DASHBOARD_TOKEN with `python -c "import secrets; print(secrets.token_urlsafe(32))"`; BASE_URL = the Render URL once known). Verify `https://<app>.onrender.com/healthz` returns `{"ok":true}`.

- [ ] **Step 4: Keep-alive + seed production**

uptimerobot.com (free): HTTP monitor on `/healthz`, 10-minute interval. Then seed production: `.venv\Scripts\python scripts/seed.py https://<app>.onrender.com` and verify the dashboard at `https://<app>.onrender.com/d/<token>`.

- [ ] **Step 5: Point SitRep at production and publish (Ruhan does the clicks)**

Studio → Interview Scorecard draft → Build → Endpoint URL = Render URL → Test step → Run all (should return real scorecards now) → Review & publish → publish to marketplace. Copy the marketplace agent URL for the writeup.

- [ ] **Step 6: Commit**

```bash
git add render.yaml LICENSE README.md
git commit -m "feat: deployment blueprint, license and documentation"
git push
```

---

### Task 14: Demo video + Kaggle writeup + final submission (Day 5, mostly Ruhan)

**Files:**
- Create: `docs/writeup.md` (draft text for the Kaggle Writeup)

- [ ] **Step 1: Record the video (2–3 min)**

Script: (1) start in SitRep — run the agent on an interview task, show the returned scorecard artifact with the panel-so-far warnings; (2) click through to the dashboard: matrix → cell slide-over evidence → Aisha's ⚠ contradiction → Daniel's ◐ gap → candidate page flag; (3) one sentence on architecture (evidence gate + free-tier fallback). Record with Win+G or OBS, single take is fine.

- [ ] **Step 2: Draft `docs/writeup.md` (≤1000 words, exact Kaggle headings)**

Sections: Inspiration / What it does / How we built it / Challenges we ran into / Accomplishments that we're proud of / What we learned / What's next. Must mention: evidence gate, claim ledger, comparison dashboard, Gemini+Groq fallback, $0 stack, honest single-tenant note. What's next: probe-question generation, debrief groupthink detection, rubric editor, multi-tenant workspaces.

- [ ] **Step 3: Submit on Kaggle (Ruhan)**

Create the Writeup on the competition page, paste `docs/writeup.md`, attach: Sitrep agent marketplace URL, GitHub repo URL, video (media gallery). Star the organizer repo. Click Submit (not draft!). Verify it shows as submitted.

- [ ] **Step 4: Commit**

```bash
git add docs/writeup.md
git commit -m "docs: kaggle writeup draft"
git push
```

---

## Task → day mapping (5 days)

- **Day 1:** Tasks 1–3 (incl. wire capture via ngrok) + Ruhan: Gemini/Groq keys, Neon + Render + UptimeRobot accounts.
- **Day 2:** Tasks 4–7.
- **Day 3:** Tasks 8–10.
- **Day 4:** Tasks 11–12, start 13 (deploy early so production soak time is long).
- **Day 5:** Finish 13 (publish), Task 14 (video, writeup, submit) with buffer.

## Verification checklist before submission

- [ ] `pytest -q` fully green
- [ ] Production `/healthz` 200; UptimeRobot monitor green for 12+ hours
- [ ] Studio "Run all" tests return real scorecards from production
- [ ] Dashboard demo beats visible in production (⚠, ◐, flag)
- [ ] Agent published on marketplace; URL works logged-out
- [ ] Repo public, MIT, README complete; no secrets in git history
- [ ] Writeup ≤1000 words, all headings, all attachments, status = Submitted
