# Interview Scorecard

**Track:** Code · **Agent:** _<Sitrep Marketplace URL — add after publishing>_ · **Repo:** https://github.com/ruhan-wankhede/sitrep-hackathon · **Demo video:** _<add link>_

## Inspiration

Every hiring loop ends the same way: five people who each scribbled different notes crowd into a fifteen-minute debrief and decide someone's career on the freshest, loudest impression in the room. Half the panel assessed the same two skills; nobody probed the others. "Culture fit" gets typed where evidence should be. The one signal that actually exists — what the candidate said, in their own words — is scattered across five documents and never reconciled. SitRep already captures every interview as a transcript. We wanted an agent that turns those transcripts into the thing hiring teams never have: a single, evidence-backed, cross-interview view of each candidate.

## What it does

Interview Scorecard runs after each interview and scores the candidate against a role rubric — with one hard rule that defines the whole product: **no score without evidence.** Every competency rating carries a verbatim quote from the meeting. If the interview produced no signal for a competency, the agent returns "Not assessed" rather than inventing a number. Because it remembers across meetings, it does what a single scorecard cannot:

- **Claim ledger & contradiction detection** — tracks factual claims (team size, tenure) and flags when a candidate says "I led a team of 8" in one interview and "we were just 3" in another.
- **Coverage & disagreement** — shows which competencies the panel still hasn't probed, and where two interviewers genuinely disagree.
- **Comparison matrix** — a live dashboard ranking every candidate for a role, each score one click from the evidence behind it.
- **Hire recommendation with a guardrail** — a banded verdict (Strong hire → No hire) where any unresolved contradiction or compliance flag *caps* the verdict at "Needs follow-up," no matter how high the raw score. In our demo the top-ranked candidate is deliberately held back because of an unresolved claim — the agent refuses to green-light over an open concern.
- **Next-interviewer brief** — turns coverage gaps and weak answers into specific questions for the next round.
- **Candidate feedback draft** — a warm, evidence-cited note the recruiter can adapt to send the candidate, delivered straight back into SitRep as a post-meeting artifact.
- **Compliance flags** — surfaces non-job-related questions (family plans, age) as a consistency-and-risk signal.

## How we built it

It is a SitRep remote (code-track) agent: a FastAPI service that SitRep POSTs each meeting to, returning a markdown scorecard plus a link to the live dashboard. The design principle is one line: **LLMs only extract and judge evidence; code does all the math and memory.** Each interview flows through three small, schema-validated LLM calls — extract Q&A and claims, score against the rubric, flag quality issues — and then every cross-interview computation (coverage, disagreement, contradictions, ranking, recommendations) is deterministic Python over Postgres. That split is what makes it trustworthy: the parts that must be consistent never touch a model.

The stack runs entirely on free tiers: Google Gemini Flash as the primary model with a Groq Llama fallback behind a single `complete_json()` interface; Neon Postgres for cross-meeting memory; and a Jinja2 + Tailwind + Alpine dashboard (with a light/dark theme) hosted on Render and kept warm by an uptime pinger.

## Challenges we ran into

Building a *reliable* agent on $0 was the real work. Three lessons stood out:

1. **Never return an error.** SitRep's webhook must always get a clean answer, so the LLM layer retries, falls back to the second provider, and degrades to a graceful artifact — never a 500 — even on malformed input or an out-of-range score.
2. **Strict schemas are brittle.** We first pinned claim categories and flag types to fixed enums. In production this quietly sank every claim-heavy interview: one off-vocabulary label from the model failed the *entire* extraction. Relaxing to normalized strings (unknown → "other") made the pipeline robust exactly where the valuable signal lives.
3. **Contradiction is subtler than "values differ."** Our first detector flagged any category with two different values — so a candidate who "owned a rollback" and "wrote a postmortem" looked like a liar. The fix was modeling which facts are *single-valued*: you have one team size and one tenure, but you can own many projects. Only single-valued categories can contradict.

## Accomplishments that we're proud of

The evidence gate and the recommendation guardrail — together they make an agent that is honest about uncertainty and will not rubber-stamp a strong-but-questionable candidate. The comparison matrix with click-to-evidence turns scattered notes into a real decision surface. And the whole system runs unattended, at zero cost, well within free-tier limits for one-interview-at-a-time use.

## What we learned

LLMs are excellent extractors and unreliable accountants — the more logic we moved out of the prompt and into code, the better the agent became. We also learned that "quality" for this product is not cleverness; it is *refusal*: refusing to score without evidence, refusing to call a multi-valued fact a contradiction, refusing to recommend a hire over an open flag. Designing for those refusals is what makes the output trustworthy enough to act on.

## What's next

An interviewer-calibration view (is one interviewer consistently harsher than the panel, or asking leading questions?); a protected-attribute detector for deeper DEI compliance; a rubric editor in the dashboard; analysing the debrief meeting itself for groupthink (score drift after the loudest voice speaks); per-workspace multi-tenancy; one-click delivery of the committee packet to Slack; and HMAC verification of SitRep's signed webhooks.
