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
