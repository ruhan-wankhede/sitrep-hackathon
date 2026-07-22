import json
from google import genai
from app.config import settings

MODEL = "gemini-2.5-flash"

def complete(prompt: str, system: str, schema) -> dict:
    client = genai.Client(api_key=settings.gemini_api_key)
    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={
            "system_instruction": system or None,
            "response_mime_type": "application/json",
            "response_schema": schema,
        },
    )
    return json.loads(resp.text)
