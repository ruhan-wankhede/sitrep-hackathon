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
    body = await request.body()
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    # Log wire capture with whatever was received
    logger.info("WIRE_CAPTURE %s %s", source, repr(body)[:4000] if body else "")

    # If payload is not a dict, use empty dict
    if not isinstance(payload, dict):
        payload = {}

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
