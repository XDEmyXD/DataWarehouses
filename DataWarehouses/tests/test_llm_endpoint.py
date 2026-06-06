import json

from app.__init__ import create_app
import app.routes as routes


class FakeLLMService:
    def __init__(self, tool_runner=None):
        self.tool_runner = tool_runner

    def is_configured(self):
        return True

    def generate_with_tools(self, prompt):
        return f"FAKE_GENERATE:{prompt}"

    def explain_asset(self, asset_id, start, end, summary_payload):
        return "EXPLAINED"


class FakeChatService:
    def __init__(self, tool_runner=None):
        self.tool_runner = tool_runner

    def summarize_asset_performance(self, asset_id, start, end):
        return {"summary": "SAMPLE_SUMMARY", "details": {"asset_id": asset_id}}


def test_prompt_calls_llm(monkeypatch):
    # Replace LLMService and ChatService before app creation so register_routes uses them
    monkeypatch.setattr(routes, "LLMService", FakeLLMService)
    monkeypatch.setattr(routes, "ChatService", FakeChatService)

    app = create_app()
    client = app.test_client()

    resp = client.post("/api/llm", json={"prompt": "Hello world"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["response"].startswith("FAKE_GENERATE")


def test_asset_calls_llm_explain(monkeypatch):
    monkeypatch.setattr(routes, "LLMService", FakeLLMService)
    monkeypatch.setattr(routes, "ChatService", FakeChatService)

    app = create_app()
    client = app.test_client()

    resp = client.post("/api/llm", json={"assetId": "BTCUSD"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["response"] == "EXPLAINED"
    assert "asset_summary" in data
