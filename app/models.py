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
