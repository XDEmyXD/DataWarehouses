import json
from flask import jsonify, render_template


def get_openapi_spec():
    """Return a small, correct OpenAPI 3.0 spec for the demo service.

    This file is intentionally compact and focused on the main endpoints used
    by the UI and tests. Keep it simple for students.
    """
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Acme Financial Analytics Demo API",
            "version": "1.0.0",
            "description": "Simple demo API: assets, sources, time-series, ingestion and analytics",
        },
        "servers": [{"url": "/", "description": "Local demo server"}],
        "paths": {
            "/api/assets": {
                "get": {
                    "tags": ["Assets"],
                    "summary": "List assets",
                    "description": "Return a paginated list of assets known to the warehouse.",
                    "parameters": [
                        {"name": "limit", "in": "query", "schema": {"type": "integer"}},
                        {"name": "offset", "in": "query", "schema": {"type": "integer"}},
                    ],
                    "responses": {
                        "200": {
                            "description": "A list of asset summary records",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/AssetsListResponse"}
                                }
                            }
                        }
                    },
                }
            },

            "/api/assets/{asset_id}": {
                "get": {
                    "tags": ["Assets"],
                    "summary": "Get asset details",
                    "parameters": [
                        {"name": "asset_id", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "responses": {
                        "200": {"description": "Asset details", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/AssetDetail"}}}},
                        "404": {"description": "Not found"}
                    }
                }
            },

            "/api/sources": {
                "get": {
                    "tags": ["Sources"],
                    "summary": "List data sources (summary)",
                    "responses": {
                        "200": {"description": "A list of known data sources (summary)", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/SourcesListResponse"}}}}
                    }
                }
            },

            "/api/sources/{source_id}": {
                "get": {
                    "tags": ["Sources"],
                    "summary": "Get data source details",
                    "parameters": [{"name": "source_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "Data source detail", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/SourceDetailResponse"}}}}, "404": {"description": "Not found"}}
                }
            },

            "/run-ingest": {
                "post": {
                    "tags": ["Ingestion"],
                    "summary": "Ingest assets",
                    "requestBody": {
                        "required": False,
                        "content": {"application/json": {"schema": {"type": "object", "properties": {"assets": {"type": "array", "items": {"type": "string"}}, "omitFields": {"type": "array", "items": {"type": "string"}}, "showResults": {"type": "boolean"}}}}}
                    },
                    "responses": {"200": {"description": "Ingest completed"}}
                }
            },

            "/run-pipeline": {
                "post": {
                    "tags": ["Ingestion"],
                    "summary": "Run full ingestion + analytics pipeline",
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
                                        "descriptive": {"type": "boolean"},
                                        "predictive": {"type": "boolean"},
                                        "async": {"type": "boolean"}
                                    }
                                },
                                "example": {"assets": ["BTCUSD"], "omitFields": ["volume"], "showResults": True}
                            }
                        }
                    },
                    "responses": {"200": {"description": "Pipeline completed", "content": {"application/json": {"example": {"status": "completed", "ingested": 22}}}}}
                }
            },

            "/ask-a-question": {
                "post": {
                    "tags": ["LLM"],
                    "summary": "Ask a single question to the platform LLM (single response)",
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "properties": {"message": {"type": "string"}, "useFunctions": {"type": "boolean"}}}, "example": {"message": "Summarize BTCUSD in one sentence."}}}},
                    "responses": {"200": {"description": "LLM replied", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/LLMResponse"}}}}, "400": {"description": "Bad request"}, "503": {"description": "LLM not configured"}}
                }
            },

            "/api/analytics/run": {
                "post": {
                    "tags": ["Analytics"],
                    "summary": "Run analytics (descriptive and/or predictive)",
                    "requestBody": {"required": False, "content": {"application/json": {"schema": {"type": "object", "properties": {"descriptive": {"type": "boolean"}, "predictive": {"type": "boolean"}, "async": {"type": "boolean"}, "showResults": {"type": "boolean"}, "assets": {"type": "array", "items": {"type": "string"}}}}}}},
                    "responses": {"200": {"description": "Analytics completed", "content": {"application/json": {"example": {"status": "completed"}}}}, "202": {"description": "Analytics started (async)"}}
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
                        {"name": "limit", "in": "query", "schema": {"type": "integer"}},
                    ],
                    "responses": {"200": {"description": "Time series records"}, "400": {"description": "Invalid request"}}
                }
            }
        },

        "components": {
            "schemas": {
                "AssetSummary": {"type": "object", "properties": {"asset_id": {"type": "string"}, "display_name": {"type": "string"}, "asset_type": {"type": "string"}}, "additionalProperties": True},
                "Asset": {"type": "object", "properties": {"asset_id": {"type": "string"}, "asset_type": {"type": "string"}, "description": {"type": "string"}}, "additionalProperties": True},
                "AssetDetail": {"type": "object", "properties": {"asset_id": {"type": "string"}, "asset": {"$ref": "#/components/schemas/Asset"}}},
                "AssetsListResponse": {"type": "object", "properties": {"assets": {"type": "array", "items": {"$ref": "#/components/schemas/AssetSummary"}}}},
                "SourceSummary": {"type": "object", "properties": {"data_source_id": {"type": "string"}, "display_name": {"type": "string"}}},
                "SourceDetailResponse": {"type": "object", "properties": {"data_source_id": {"type": "string"}, "source": {"type": "object", "additionalProperties": True}}},
                "SourcesListResponse": {"type": "object", "properties": {"sources": {"type": "array", "items": {"$ref": "#/components/schemas/SourceSummary"}}}},
                "TimeSeriesRecord": {"type": "object", "properties": {"asset_id": {"type": "string"}, "data_source_id": {"type": "string"}, "business_date": {"type": "string"}, "metrics": {"type": "object", "additionalProperties": True}}},
                "LLMResponse": {"type": "object", "properties": {"message": {"type": ["string", "object"]}}},
            }
        }
    }


def register_openapi(app):
    @app.route("/api/openapi.json", methods=["GET"])
    def openapi_json():
        return jsonify(get_openapi_spec())

    @app.route("/api/docs", methods=["GET"])
    def swagger_ui():
        return render_template("swagger_ui.html")
