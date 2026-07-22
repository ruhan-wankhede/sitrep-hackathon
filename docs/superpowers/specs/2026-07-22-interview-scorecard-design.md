# Interview Scorecard — Design Spec

**Date:** 2026-07-22
**Target:** SitRep AI Hackathon (Kaggle), Code Track. Submission deadline in ~5 days (2026-07-27).
**Product name:** Interview Scorecard (draft agent already saved in Ruhan's SitRep Studio).

## 1. Product summary

A SitRep marketplace agent that turns interview meetings into evidence-backed scorecards, and — because it remembers across meetings — maintains a claim-consistency ledger per candidate and a candidate comparison matrix per role, served as a hosted dashboard.

Pitch line: **LLMs only extract and judge evidence; code does all the math and memory.**

Per interview:
- Structured scorecard against a rubric: each competency scored 1–4 with evidence quotes from the meeting summary, or **"not assessed"** when evidence is absent. A score without evidence is demoted to "not assessed" by code — the model cannot hallucinate a rating past that gate.
- Interview-quality flags: leading questions, non-job-related topics (compliance risk), vague "culture fit" feedback with no behavioral evidence.

Across interviews (the code-track moat):
- Competency coverage matrix for the panel ("system design still unprobed").
- Interviewer disagreement detection (score spread ≥ 2 on the same competency).
- Claim-consistency ledger: factual claims (team size, tenure, ownership, metrics) tracked per candidate; contradictions across interviews are flagged.
- Candidate comparison matrix per role — the dashboard centerpiece.

Out of scope for v1 (listed in writeup "What's next"): generated probe questions for the next interviewer, debrief groupthink detection, evidence-grounded candidate feedback emails, dashboard rubric editor.

## 2. Platform contract (verified in SitRep app)

- Build method: **Remote (host your own)** — SitRep POSTs task context to `<endpoint>/run` (production) and `<endpoint>/test` (built-in test harness).
- Input carries: task (title, description), **meeting summary (not the raw transcript)**, attendees, and `agent.instructions` (free-text field configured by the installer, passed through verbatim).
- Response: `{"artifacts": [{"type": "markdown", "title": ..., "content": ...}]}`.
- Trigger: task types; the draft agent subscribes to **Summary** (revisit on day 1 whether Custom/Document should be added).
- The Studio Test step lets us paste arbitrary task title + meeting summary + detail and fire it at the live endpoint — this is the primary development and demo-seeding mechanism (no staged Zoom calls needed for iteration).

**Day-1 empirical checks:** exact JSON field names of the POST body; whether any workspace/install identifier arrives (header or body); SitRep's webhook timeout. The reference handler shows the shape but not the exact wire format.

## 3. Constraints

- **No paid services anywhere.** LLM: Google Gemini free tier (primary) + Groq free tier (fallback). Hosting: Render free tier + UptimeRobot free keep-alive. DB: Neon free Postgres. All no-card signups.
- Judges must be able to evaluate the live agent throughout the judging period; winners may be asked to verify functionality (Rules §13). The stack must therefore run unattended at $0.
- Kaggle writeup ≤ 1000 words, prescribed sections; public GitHub repo, MIT license; short demo video (online hackathon — no live presentation).

## 4. Architecture

One FastAPI application (Python 3.12), one Render web service, one Neon database.

Routes:
- `POST /run`, `POST /test` — SitRep contract; same handler, rows tagged `source=run|test`.
- `GET /d/{token}` — dashboard home (roles → candidates, open warnings).
- `GET /d/{token}/role/{role_id}` — candidate comparison matrix.
- `GET /d/{token}/candidate/{candidate_id}` — candidate detail (timeline, scorecards, flags, claims).
- `GET /healthz` — UptimeRobot target (pings every 10 min to defeat Render's 15-min sleep).

Module boundaries:
- `llm/` — exposes exactly one function: `complete_json(prompt, schema) -> validated dict`. Encapsulates Gemini primary, retry ×2 with backoff, Groq fallback, Pydantic validation (validation failure = failed attempt). No other module knows which provider answered.
- `pipeline/` — per-interview orchestration (extract → rubric → score → flags → persist → compose artifact).
- `analytics/` — deterministic cross-interview logic: coverage, disagreements, contradiction candidates. Pure functions over stored rows; no LLM except one confirmation call per suspected contradiction pair.
- `web/` — dashboard routes + Jinja2 templates (Tailwind + Alpine.js via CDN; no build step).
- `rubrics/` — built-in role-family rubrics (engineering, sales, PM, generic) as data files + instructions-override parser.

Tenancy: if SitRep sends a workspace/install identifier, key everything on it (multi-tenant). Otherwise single-tenant per deployment with one dashboard token — acceptable for judging and stated honestly in the writeup.

## 5. Data model (Neon Postgres, SQLAlchemy)

- **roles** — id, title, resolved rubric (JSONB), dashboard token, created_at
- **candidates** — id, normalized name, role FK, created_at
- **interviews** — id, candidate FK, interviewer, meeting date, summary text, raw request payload (JSONB), source (`run`/`test`), dedup hash, created_at
- **scorecards** — id, interview FK, competency, score (int 1–4, nullable; null = "not assessed"), evidence (JSONB list), rationale
- **claims** — id, candidate FK, interview FK, category (enum: `team_size`, `tenure`, `role_scope`, `project_ownership`, `metric`, `other`), statement, extracted value
- **flags** — id, interview FK, type (`leading_question`, `non_job_related`, `vague_feedback`), excerpt, note

Idempotency: dedup hash = SHA-256 of (candidate, interviewer, summary). A duplicate delivery updates rather than double-writes.

## 6. LLM pipeline (Approach B — staged, deterministic core)

Per incoming request:
1. **Classify + extract** (LLM call ①, strict JSON schema): is this an interview? If not → return a polite one-line artifact ("this doesn't look like an interview meeting") and stop. If yes: candidate name, role title, interviewer, Q&A exchanges, categorized factual claims.
2. **Resolve rubric** (code): competencies parsed from `agent.instructions` if present, else keyword-match role title to a family, else generic rubric.
3. **Score** (LLM call ②): input is *only the extracted evidence* + rubric; output per competency: score, evidence items, rationale. Code enforces the evidence gate (no evidence → "not assessed").
4. **Flags** (LLM call ③): quality issues with excerpts.
5. **Persist**; run deterministic analytics: coverage, disagreements, contradiction candidates (same candidate + same claim category + conflicting values), each candidate pair confirmed by one small LLM call to kill false positives.
6. **Compose markdown artifact**: this interview's scorecard, panel-so-far snapshot (gaps, disagreements, contradiction warnings), link to the dashboard.

Latency budget: 3 sequential Gemini Flash calls ≈ 3–6 s — inside any sane webhook timeout (verify day 1). Quota budget: ~4 calls/interview vs hundreds/day free — judging cannot exhaust it.

## 7. Dashboard UX

Dark premium aesthetic; server-rendered Jinja2 + Tailwind + Alpine.js. Design principle: **every number is one click from its evidence.**

- **Pipeline home:** role cards with candidate counts and open-warning badges.
- **Comparison matrix (centerpiece):** competencies as rows, candidates as columns. Cells: panel-averaged score as filled-dot scale, color-coded (emerald 4 → amber 2 → red 1), gray hatch for "not assessed". Column headers badge ⚠ claim contradiction and ◐ incomplete coverage. Click a cell → slide-over with per-interviewer scores, evidence, rationale. Click ⚠ → claim ledger showing both conflicting statements and their source interviews.
- **Candidate detail:** interview timeline, full scorecards, flags, claims; doubles as the pre-round briefing page ("what's still unprobed").
- Empty states designed deliberately (e.g., "panel in progress — 1 of N perspectives") since judges will poke with sparse data.

## 8. Reliability & error handling

- LLM chain: Gemini → retry ×2 → Groq → graceful failure artifact (never a 500 to SitRep).
- All LLM output Pydantic-validated; invalid = retry.
- Non-interview input handled as a designed, polite behavior (scored by judges, not an edge case).
- Idempotent writes via dedup hash.
- Render sleep defeated by UptimeRobot on `/healthz`; DB pool sized for Neon free tier; secrets via Render env vars; `.env.example` in repo.

## 9. Testing

- **Unit (pure, no LLM/DB):** rubric resolution + instructions parsing, evidence-gate demotion, contradiction detection, disagreement/coverage math.
- **Integration:** FastAPI TestClient through `/run` with faked `complete_json`; one manually-run live-LLM smoke test.
- **Fixtures double as demo data:** candidate A ×3 interviews (uneven coverage, one planted claim contradiction, one planted non-job-related question), candidate B ×2 interviews (so the matrix has two columns).

## 10. Demo & submission plan

- **Video (2–3 min screen recording, no production):** one real captured mock call in SitRep → artifact appears → dashboard: matrix → cell click → evidence → contradiction ledger.
- **Kaggle writeup (≤1000 words, prescribed headings):** Inspiration / What it does / How you built it / Challenges (free-tier engineering as a feature) / Accomplishments / What you learned / What's next (probe questions, groupthink detector, rubric editor). Attach: published agent URL, GitHub repo link, video.
- **Repo:** public, MIT license, README with architecture diagram, setup instructions, deployment instructions (explicitly requested for Code Track), `.env.example`.
- **Publish** the agent from the saved Studio draft with the Render endpoint (Ruhan clicks publish). Keep service + DB + keys alive through the judging period (winner verification, Rules §13).
- Final Kaggle submission must be *submitted*, not draft, before the deadline.

## 11. Five-day plan

- **Day 1:** Scaffold repo; `llm/` layer with both providers; ngrok tunnel; point Studio draft endpoint at tunnel; fire Studio tests to capture the exact wire format; adjust models; hello-world artifact round-trip. Get Gemini/Groq keys (Ruhan), Neon DB, Render service shell.
- **Day 2:** Pipeline calls ①②③ + rubric resolution + evidence gate, against fixture transcripts, with unit tests.
- **Day 3:** Persistence, analytics (coverage, disagreements, claim ledger), artifact composition with panel snapshot.
- **Day 4:** Dashboard (all three screens), deploy to Render, UptimeRobot, publish agent from Studio, marketplace listing copy.
- **Day 5:** Record video, write writeup, repo polish (README, MIT, instructions), submit on Kaggle with buffer.

## 12. Risks & mitigations

- **Wire format differs from reference snippet** → day-1 empirical capture before any pipeline work.
- **No workspace identifier in payload** → single-tenant fallback (decided; not a blocker).
- **Gemini free-tier rate limit during judging** → Groq fallback chain, tested.
- **Render cold start despite pinger** → UptimeRobot 10-min interval well under the 15-min sleep threshold; `/healthz` is trivially cheap.
- **Neon free-tier idle suspend (~5 min)** → first query auto-resumes in <1 s on modern Neon; acceptable.
- **Summary quality too thin for evidence** → prompts treat SitRep's summary as the source of truth and cite what exists; "not assessed" absorbs thin inputs honestly.
