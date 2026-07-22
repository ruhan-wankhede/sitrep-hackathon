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
    return artifact_response("Interview Scorecard", f"Received task: {normalized.title or '(untitled)'}")

@app.post("/run")
async def run(request: Request):
    return await _handle(request, "run")

@app.post("/test")
async def test(request: Request):
    return await _handle(request, "test")
