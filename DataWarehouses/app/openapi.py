
import json
from flask import jsonify, render_template


def get_openapi_spec():
    """Return a minimal, well-formed OpenAPI 3.0 spec for the service.

    The spec focuses on the endpoints used by the UI: assets, ingestion, analytics and
    the time-series endpoint. Ordering places ingestion first so the UI surfaces those controls above data fetch endpoints.
    """
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Acme Financial Analytics Demo API",
            "version": "1.0.0",
            "description": "Acme demo API - assets, time-series, ingestion and analytics",
        },
        "servers": [{"url": "/", "description": "Local demo server"}],
        "paths": {
            "/api/assets": {
                "get": {
                    "tags": ["Assets"],
                    "summary": "List Assets",
                    "parameters": [
                        {"name": "limit", "in": "query", "schema": {"type": "integer"}},
                        {"name": "offset", "in": "query", "schema": {"type": "integer"}},
                    ],
                    "responses": {"200": {"description": "Assets returned."}},
                }
            },
            "/api/assets/{asset_id}": {
                "get": {
                    "tags": ["Assets"],
                    "summary": "Get asset details",
                    "parameters": [{"name": "asset_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "Asset details"}, "404": {"description": "Not found"}},
                }
            },
            "/run-ingest": {
                "post": {
                    "tags": ["Ingestion"],
                    "summary": "Ingest assets",
                    "description": "Ingest a list of assets. Use `omitFields` to remove metric fields before storage and `showResults` to return recent backend records.",
                    "requestBody": {
                        "required": False,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "assets": {"type": "array", "items": {"type": "string"}},
                                        "omitFields": {"type": "array", "items": {"type": "string"}},
                                        "showResults": {"type": "boolean"},
                                    },
                                },
                                "example": {"assets": ["BTCUSD"], "omitFields": ["volume"], "showResults": True},
                            }
                        }
                    },
                    "responses": {"200": {"description": "Ingest completed"}},
                }
            },
            "/run-pipeline": {
                "post": {
                    "tags": ["Ingestion"],
                    "summary": "Run full ingestion + analytics pipeline",
                    "requestBody": {"required": False},
                    "responses": {"200": {"description": "Pipeline completed"}},
                }
            },
            "/api/analytics/run": {
                "post": {
                    "tags": ["Analytics"],
                    "summary": "Run analytics (descriptive and/or predictive)",
                    "description": "Trigger descriptive and/or predictive analytics. Use `showResults` to return results in the response. Set `async` to true to run in background.",
                    "requestBody": {
                        "required": False,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "descriptive": {"type": "boolean"},
                                        "predictive": {"type": "boolean"},
                                        "async": {"type": "boolean"},
                                        "showResults": {"type": "boolean"},
                                        "assets": {"type": "array", "items": {"type": "string"}}
                                    },
                                },
                                "example": {"descriptive": True, "predictive": True, "async": False, "showResults": True}
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Analytics completed",
                            "content": {
                                "application/json": {
                                    "example": {
                                        "status": "completed",
                                        "descriptive_count": 22,
                                        "predictive_count": 22,
                                        "descriptive": [{"asset_id": "BTCUSD", "business_date_year": 2026, "record_count": 75}],
                                        "predictive": [{"asset_id": "BTCUSD", "predicted_next_close_price": 99651.33}]
                                    }
                                }
                            }
                        },
                        "202": {"description": "Analytics started (async)"}
                    }
                }
            },
            "/api/time-series": {
                "get": {
                    "tags": ["Data"],
                    "summary": "Fetch time-series data",
                    "parameters": [
                        {"name": "assetId", "in": "query", "required": True, "schema": {"type": "string"}},
                        {"name": "dataSourceId", "in": "query", "required": False, "schema": {"type": "string"}},
                        {"name": "startBusinessDate", "in": "query", "schema": {"type": "string", "format": "date"}},
                        {"name": "endBusinessDate", "in": "query", "schema": {"type": "string", "format": "date"}},
                    ],
                    "responses": {"200": {"description": "Time series records"}, "400": {"description": "Invalid request"}},
                }
            }
        },
    }


def register_openapi(app):
	@app.route("/api/openapi.json", methods=["GET"])
	def openapi_json():
		return jsonify(get_openapi_spec())

	@app.route("/api/docs", methods=["GET"])
	def swagger_ui():
		return render_template("swagger_ui.html")

