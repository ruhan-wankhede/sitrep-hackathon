import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.llm import LLMUnavailable
from app.pipeline import passes
from app.pipeline.artifact import compose_markdown, panel_snapshot
from app.pipeline.persist import save_interview
from app.pipeline.probes import refresh_brief
from app.rubrics import resolve_rubric
from app.sitrep import (
    NormalizedTask, artifact_response, build_response, link_artifact, markdown_artifact,
)

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
        feedback = refresh_brief(session, interview.candidate_id, extraction.role_title,
                                 extraction.candidate_name, snapshot["coverage"]["unassessed"])
        name = extraction.candidate_name.title() or "Candidate"
        artifacts = [markdown_artifact(f"Scorecard: {name}",
                                       compose_markdown(interview, scoreset, flagset, snapshot))]
        if feedback:
            artifacts.append(markdown_artifact(f"Draft candidate feedback — {name}", feedback))
        artifacts.append(link_artifact(
            "Open the live panel dashboard",
            f"{settings.base_url}/d/{settings.dashboard_token}/candidate/{interview.candidate_id}"))
        logs = [
            f"role={extraction.role_title or 'unknown'}",
            f"competencies_scored={sum(1 for s in scoreset.scores if s.score is not None)}",
            f"unprobed={len(snapshot['coverage']['unassessed'])}",
            f"contradictions={len(snapshot['contradictions'])}",
        ]
        return build_response(artifacts, logs)
    except LLMUnavailable as e:
        logger.error("llm unavailable: %s", e)
        return artifact_response(
            "Interview Scorecard",
            "We couldn't analyze this meeting right now (AI providers unavailable). "
            "Your meeting data is safe — re-run this task in a few minutes.")
    except Exception:
        logger.exception("unexpected error in run_pipeline")
        return artifact_response(
            "Interview Scorecard",
            "Something went wrong while analyzing this meeting. Your meeting data in SitRep "
            "is unaffected — re-run this task in a few minutes.")
