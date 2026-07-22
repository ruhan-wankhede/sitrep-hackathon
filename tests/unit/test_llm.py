import pytest
from pydantic import BaseModel
import app.llm as llm

class Out(BaseModel):
    x: int

def test_returns_validated_model_from_first_provider(monkeypatch):
    monkeypatch.setattr(llm, "PROVIDERS", [lambda **kw: {"x": 1}])
    assert llm.complete_json("p", Out).x == 1

def test_falls_back_when_first_provider_fails(monkeypatch):
    def bad(**kw): raise RuntimeError("quota")
    monkeypatch.setattr(llm, "PROVIDERS", [bad, lambda **kw: {"x": 2}])
    monkeypatch.setattr(llm, "RETRY_SLEEP", 0)
    assert llm.complete_json("p", Out).x == 2

def test_invalid_json_counts_as_failure(monkeypatch):
    monkeypatch.setattr(llm, "PROVIDERS", [lambda **kw: {"x": "not-an-int-fixable"}, lambda **kw: {"wrong": 1}])
    monkeypatch.setattr(llm, "RETRY_SLEEP", 0)
    # first provider coerces "not-an-int-fixable"? no — pydantic strict enough to fail, falls to second, also fails
    with pytest.raises(llm.LLMUnavailable):
        llm.complete_json("p", Out)
