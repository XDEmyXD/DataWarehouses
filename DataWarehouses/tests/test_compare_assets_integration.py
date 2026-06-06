import json
from datetime import datetime
import hashlib

from app.mistral_adapter import MistralAdapter
from app.mcp_tools import call_tool
from db.database import timeseries_collection


def _make_ingest_id(asset, date, close):
    payload = {"asset": asset, "date": date, "close": close}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def test_mistral_tool_call_compare_assets(monkeypatch):
    # Insert deterministic fixtures for BTCUSD and ETHUSD
    docs = [
        {"asset_id": "BTCUSD", "data_source_id": "TEST", "business_date": "2026-06-01", "metrics": {"close": 100.0}, "system_date": datetime.utcnow().isoformat() + "Z", "ingest_id": _make_ingest_id("BTCUSD", "2026-06-01", 100.0)},
        {"asset_id": "BTCUSD", "data_source_id": "TEST", "business_date": "2026-06-02", "metrics": {"close": 110.0}, "system_date": datetime.utcnow().isoformat() + "Z", "ingest_id": _make_ingest_id("BTCUSD", "2026-06-02", 110.0)},
        {"asset_id": "BTCUSD", "data_source_id": "TEST", "business_date": "2026-06-03", "metrics": {"close": 105.0}, "system_date": datetime.utcnow().isoformat() + "Z", "ingest_id": _make_ingest_id("BTCUSD", "2026-06-03", 105.0)},
        {"asset_id": "ETHUSD", "data_source_id": "TEST", "business_date": "2026-06-01", "metrics": {"close": 10.0}, "system_date": datetime.utcnow().isoformat() + "Z", "ingest_id": _make_ingest_id("ETHUSD", "2026-06-01", 10.0)},
        {"asset_id": "ETHUSD", "data_source_id": "TEST", "business_date": "2026-06-02", "metrics": {"close": 11.0}, "system_date": datetime.utcnow().isoformat() + "Z", "ingest_id": _make_ingest_id("ETHUSD", "2026-06-02", 11.0)},
        {"asset_id": "ETHUSD", "data_source_id": "TEST", "business_date": "2026-06-03", "metrics": {"close": 12.0}, "system_date": datetime.utcnow().isoformat() + "Z", "ingest_id": _make_ingest_id("ETHUSD", "2026-06-03", 12.0)},
    ]

    inserted_ids = timeseries_collection.insert_many(docs).inserted_ids

    try:
        adapter = MistralAdapter()

        # Sequence of fake API responses: first asks to call the tool, second returns assistant text
        responses = [
            {"output": json.dumps({"tool": "compare_assets", "params": {"assetIdA": "BTCUSD", "assetIdB": "ETHUSD", "dataSourceId": "TEST", "startBusinessDate": "2026-06-01", "endBusinessDate": "2026-06-04"}})},
            {"output": "Comparison complete: BTCUSD vs ETHUSD summarized."},
        ]

        def fake_call_api(payload, timeout=30):
            return responses.pop(0)

        monkeypatch.setattr(adapter, "_call_api", fake_call_api)

        messages = [{"role": "user", "content": "Compare BTC and ETH for me."}]
        functions = []  # adapter only uses this for prompt, not required for parsing

        result = adapter.generate_with_tools(messages, functions, tool_runner=call_tool, max_steps=2)

        assert "Comparison complete" in result

        # Also call the tool directly to assert deterministic numeric outputs
        tool_out = call_tool("compare_assets", {"assetIdA": "BTCUSD", "assetIdB": "ETHUSD", "dataSourceId": "TEST", "startBusinessDate": "2026-06-01", "endBusinessDate": "2026-06-04"})
        assert tool_out["status"] == "success"
        data = tool_out.get("data", {})
        assert data.get("statsA") and data.get("statsB")
        # percent changes: BTC ((105-100)/100)=5.0; ETH ((12-10)/10)=20.0
        assert abs(data["statsA"]["percent_change"] - 5.0) < 0.001
        assert abs(data["statsB"]["percent_change"] - 20.0) < 0.001

    finally:
        # Cleanup fixtures
        timeseries_collection.delete_many({"data_source_id": "TEST"})
