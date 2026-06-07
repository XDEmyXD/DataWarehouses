from app.__init__ import create_app
from db.database import assets_collection, sources_collection, timeseries_collection
from datetime import datetime


def test_api_asset_details_returns_linked_sources():
    app = create_app()
    client = app.test_client()

    asset_id = "TESTASSET"
    data_source_id = "TEST-SOURCE"

    asset_doc = {
        "asset_id": asset_id,
        "active": True,
        "asset_type": "test_asset",
        "description": "Test asset for API details",
        "region": "Testland",
        "instrument_class": "equity",
        "first_seen": datetime.utcnow().isoformat() + "Z",
        "last_seen": datetime.utcnow().isoformat() + "Z",
        "supported_indicators": ["business_date", "close_price"],
    }
    source_doc = {
        "data_source_id": data_source_id,
        "active": True,
        "display_name": "Test Source",
        "description": "Test data source",
        "attributes": ["business_date", "close_price"],
        "vendor_id": "TESTVENDOR",
        "vendor_name": "Test Vendor",
    }
    ts_doc_1 = {
        "asset_id": asset_id,
        "data_source_id": data_source_id,
        "business_date": "2026-06-01",
        "system_date": datetime.utcnow().isoformat() + "Z",
        "metrics": {"close": 100.0},
        "attributes": ["business_date", "close_price"],
        "provenance": {"source_name": "Test Source", "source_url": None, "query_parameters": {}},
        "ingest_id": "test-ingest-1",
    }
    ts_doc_2 = {
        "asset_id": asset_id,
        "data_source_id": data_source_id,
        "business_date": "2026-06-02",
        "system_date": datetime.utcnow().isoformat() + "Z",
        "metrics": {"close": 105.0},
        "attributes": ["business_date", "close_price"],
        "provenance": {"source_name": "Test Source", "source_url": None, "query_parameters": {}},
        "ingest_id": "test-ingest-2",
    }

    assets_collection.insert_one(asset_doc)
    sources_collection.insert_one(source_doc)
    timeseries_collection.insert_many([ts_doc_1, ts_doc_2])

    try:
        resp = client.get(f"/api/assets/{asset_id}/details")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["asset_id"] == asset_id
        assert data["details"]["asset"]["asset_id"] == asset_id
        assert isinstance(data["details"]["linked_data_sources"], list)
        assert data["details"]["linked_data_sources"][0]["data_source_id"] == data_source_id

        resp_range = client.get(
            f"/api/assets/{asset_id}/details?startBusinessDate=2026-06-01&endBusinessDate=2026-06-02"
        )
        assert resp_range.status_code == 200
        range_data = resp_range.get_json()
        assert range_data["historical_records"]
        returned_dates = {r["business_date"] for r in range_data["historical_records"]}
        assert returned_dates == {"2026-06-01", "2026-06-02"}
    finally:
        assets_collection.delete_one({"asset_id": asset_id})
        sources_collection.delete_one({"data_source_id": data_source_id})
        timeseries_collection.delete_many({"ingest_id": {"$in": ["test-ingest-1", "test-ingest-2"]}})


def test_api_export_monthly_data_returns_active_asset_records():
    app = create_app()
    client = app.test_client()

    asset_id = "EXPORTASSET"
    data_source_id = "EXPORT-SOURCE"

    asset_doc = {
        "asset_id": asset_id,
        "active": True,
        "asset_type": "test_asset",
        "description": "Test asset for export",
        "region": "Testland",
        "instrument_class": "equity",
        "first_seen": datetime.utcnow().isoformat() + "Z",
        "last_seen": datetime.utcnow().isoformat() + "Z",
        "supported_indicators": ["business_date", "close_price"],
    }
    ts_doc_1 = {
        "asset_id": asset_id,
        "data_source_id": data_source_id,
        "business_date": "2026-06-01",
        "system_date": datetime.utcnow().isoformat() + "Z",
        "metrics": {"close": 100.0},
        "attributes": ["business_date", "close_price"],
        "provenance": {"source_name": "Export Source", "source_url": None, "query_parameters": {}},
        "ingest_id": "export-test-ingest-1",
    }
    ts_doc_2 = {
        "asset_id": asset_id,
        "data_source_id": data_source_id,
        "business_date": "2026-06-02",
        "system_date": datetime.utcnow().isoformat() + "Z",
        "metrics": {"close": 110.0},
        "attributes": ["business_date", "close_price"],
        "provenance": {"source_name": "Export Source", "source_url": None, "query_parameters": {}},
        "ingest_id": "export-test-ingest-2",
    }

    assets_collection.insert_one(asset_doc)
    timeseries_collection.insert_many([ts_doc_1, ts_doc_2])

    try:
        resp = client.get("/api/export/monthly-data?endBusinessDate=2026-06-02&days=2")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["startBusinessDate"] == "2026-06-01"
        assert data["endBusinessDate"] == "2026-06-02"
        assert data["asset_count"] >= 1
        our_records = [record for record in data["records"] if record["asset_id"] == asset_id]
        assert {record["business_date"] for record in our_records} == {"2026-06-01", "2026-06-02"}
    finally:
        assets_collection.delete_one({"asset_id": asset_id})
        timeseries_collection.delete_many({"ingest_id": {"$in": ["export-test-ingest-1", "export-test-ingest-2"]}})
