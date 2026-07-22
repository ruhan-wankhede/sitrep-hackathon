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
        flags = session.query(FlagRow).filter(FlagRow.interview_id.in_(list(iv_by_id) or [0])).all()
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
