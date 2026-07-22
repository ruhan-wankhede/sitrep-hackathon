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
    except Exception:
        logger.exception("unexpected error in run_pipeline")
        return artifact_response(
            "Interview Scorecard",
            "Something went wrong while analyzing this meeting. Your meeting data in SitRep "
            "is unaffected — re-run this task in a few minutes.")
