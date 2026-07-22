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
