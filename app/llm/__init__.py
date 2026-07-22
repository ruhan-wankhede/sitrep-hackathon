import logging
import time
from pydantic import BaseModel, ValidationError

logger = logging.getLogger("llm")

class LLMUnavailable(Exception):
    pass

RETRY_SLEEP = 1.5
ATTEMPTS_PER_PROVIDER = 2

def _load_providers():
    from app.llm import gemini, groq
    return [gemini.complete, groq.complete]

PROVIDERS = None  # lazy; tests monkeypatch this

def complete_json(prompt: str, schema: type[BaseModel], system: str = "") -> BaseModel:
    providers = PROVIDERS if PROVIDERS is not None else _load_providers()
    last_err = None
    for provider in providers:
        for attempt in range(ATTEMPTS_PER_PROVIDER):
            try:
                raw = provider(prompt=prompt, system=system, schema=schema)
                return schema.model_validate(raw)
            except (Exception, ValidationError) as e:
                last_err = e
                logger.warning("provider %s attempt %d failed: %s",
                               getattr(provider, "__module__", provider), attempt + 1, e)
                if attempt + 1 < ATTEMPTS_PER_PROVIDER:
                    time.sleep(RETRY_SLEEP * (attempt + 1))
    raise LLMUnavailable(f"all providers failed: {last_err}")
