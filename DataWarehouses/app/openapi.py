
import json
from flask import jsonify, render_template


def get_openapi_spec():
    """Return a minimal OpenAPI 3.0 spec for the service with assets first.

    The spec presents Assets endpoints first (list and details), then Sources
    (summary list and detail by id), followed by ingestion, analytics and time-series.
    """
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Acme Financial Analytics Demo API",
            "version": "1.0.0",
            "description": "Acme demo API - assets, data sources, time-series, ingestion and analytics",
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
                                    "schema": {"type": "array", "items": {"$ref": "#/components/schemas/AssetSummary"}},
                                    "example": [
                                        {"asset_id": "BTCUSD", "display_name": "Bitcoin / USD", "asset_type": "CRYPTO"},
                                        {"asset_id": "AAPL", "display_name": "Apple Inc.", "asset_type": "EQUITY"}
                                    ],
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
                                    
                        "200": {"description": "Asset details", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/AssetDetail"}}}},
                        "404": {"description": "Not found"},
                                                "example": {"assets": ["BTCUSD"], "omitFields": ["volume"], "showResults": True}
                }
            },
            "/api/sources": {
                                    "responses": {"200": {"description": "Pipeline completed", "content": {"application/json": {"example": {"status": "completed", "ingested": 22, "descriptive_count": 22, "predictive_count": 22, "ingest_results": [{"asset": "BTCUSD", "status": "ingested"}]}}}}},
                            "/ask": {
                    "summary": "List data sources (summary)",
                    "description": "Return limited identification information about all supported data sources (e.g. `dataSourceId`, `display_name`, `vendor_id`).",
                    "responses": {
                        "200": {
                            "description": "A list of known data sources (summary)",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "array", "items": {"$ref": "#/components/schemas/SourceSummary"}},
                                    "example": [
                                        {"data_source_id": "NASDAQ_API", "display_name": "Nasdaq Data Link", "vendor_id": "NASDAQ"},
                                        {"data_source_id": "FALLBACK_SAMPLE", "display_name": "Fallback Sample Feed", "vendor_id": "ACME"}
                                    ],
                                }
                            }
                        }
                    }
                }
            },
            "/ask-a-question": {
                "post": {
                    "tags": ["Analytics", "LLM"],
                    "summary": "Ask a single question to the platform LLM (single response)",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"type": "object", "properties": {"message": {"type": "string"}, "useFunctions": {"type": "boolean"}}},
                                "example": {"message": "Summarize BTCUSD in one sentence."}
                            }
                        }
                    },
                    "responses": {
                        "200": {"description": "LLM replied", "content": {"application/json": {"schema": {"type": "object", "properties": {"status": {"type": "string"}, "llm_response": {"$ref": "#/components/schemas/LLMResponse"}}}}}},
                        "400": {"description": "Bad request"},
                        "503": {"description": "LLM not configured"}
                    }
                }
            },
            "/api/sources/{source_id}": {
                "get": {
                    "tags": ["Sources"],
                    "summary": "Get data source details",
                    "description": "Return all metadata and schema details for a given data source identified by `source_id` (e.g. attributes, vendor info, activity dates).",
                    "parameters": [{"name": "source_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {
                        "200": {"description": "Data source detail", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/SourceDetail"}}}},
                        "404": {"description": "Not found"},
                    },
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
                                        "async": {"type": "boolean"},
                                        "message": {"type": "string"},
                                        "useFunctions": {"type": "boolean"}
                                    }
                                },
                                "example": {"assets": ["BTCUSD"], "omitFields": ["volume"], "showResults": True, "message": "Summarize BTCUSD in one sentence."}
                            }
                        }
                    },
                    "responses": {"200": {"description": "Pipeline completed", "content": {"application/json": {"example": {"status": "completed", "ingested": 22, "descriptive_count": 22, "predictive_count": 22, "ingest_results": [{"asset": "BTCUSD", "status": "ingested"}], "llm_response": {"message": "BTCUSD had steady gains over the period."}}}}}},
            "/ask": {
                "post": {
                    "tags": ["Analytics", "LLM"],
                    "summary": "Ask a single question to the platform LLM",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"type": "object", "properties": {"message": {"type": "string"}, "useFunctions": {"type": "boolean"}}},
                                "example": {"message": "Summarize BTCUSD in one sentence."}
                            }
                        }
                    },
                    "responses": {
                        "200": {"description": "LLM replied", "content": {"application/json": {"schema": {"type": "object", "properties": {"status": {"type": "string"}, "llm_response": {"$ref": "#/components/schemas/LLMResponse"}}}}}},
                        "400": {"description": "Bad request"},
                        "503": {"description": "LLM not configured"}
                    }
                }
            },
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
        "components": {
            "schemas": {
                "AssetSummary": {
                    "type": "object",
                    "properties": {
                        "asset_id": {"type": "string"},
                        "display_name": {"type": "string"},
                        "asset_type": {"type": "string"}
                    },
                    "additionalProperties": True
                },
                "Asset": {
                    "type": "object",
                    "properties": {
                        "asset_id": {"type": "string"},
                        "asset_type": {"type": "string"},
                        "description": {"type": "string"},
                        "region": {"type": "string"},
                        "instrument_class": {"type": "string"},
                        "first_seen": {"type": "string"},
                        "last_seen": {"type": "string"},
                        "active": {"type": "boolean"},
                        "supported_indicators": {"type": "array", "items": {"type": "string"}},
                        "primary_vendor_id": {"type": "string"},
                        "primary_vendor_name": {"type": "string"},
                        "primary_vendor_description": {"type": "string"}
                    },
                    "additionalProperties": True
                },
                "AssetDetail": {
                    "type": "object",
                    "properties": {
                        "asset_id": {"type": "string"},
                        "asset": {"$ref": "#/components/schemas/Asset"}
                    }
                },
                "AssetsListResponse": {
                    "type": "object",
                    "properties": {"assets": {"type": "array", "items": {"$ref": "#/components/schemas/Asset"}}}
                },
                "SourceSummary": {
                    "type": "object",
                    "properties": {
                        "data_source_id": {"type": "string"},
                        "display_name": {"type": "string"},
                        "vendor_id": {"type": "string"}
                    },
                    "additionalProperties": True
                },
                "Source": {
                    "type": "object",
                    "properties": {
                        "data_source_id": {"type": "string"},
                        "display_name": {"type": "string"},
                        "description": {"type": "string"},
                        "attributes": {"type": "array", "items": {"type": "string"}},
                        "vendor_id": {"type": "string"},
                        "vendor_name": {"type": "string"},
                        "vendor_description": {"type": "string"},
                        "first_seen": {"type": "string"},
                        "last_seen": {"type": "string"},
                        "supported_indicators": {"type": "array", "items": {"type": "string"}},
                        "active": {"type": "boolean"}
                    },
                    "additionalProperties": True
                },
                "SourceDetailResponse": {
                    "type": "object",
                    "properties": {
                        "data_source_id": {"type": "string"},
                        "source": {"$ref": "#/components/schemas/Source"}
                    }
                },
                "SourcesListResponse": {
                    "type": "object",
                    "properties": {"sources": {"type": "array", "items": {"$ref": "#/components/schemas/Source"}}}
                },
                "IngestResultEntry": {
                    "type": "object",
                    "properties": {"asset": {"type": "string"}, "status": {"type": "string"}, "error": {"type": "string"}}
                },
                "IngestResponse": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "ingested": {"type": "integer"},
                        "recent_records": {"type": "array", "items": {"$ref": "#/components/schemas/TimeSeriesRecord"}}
                    }
                },
                "DescriptiveEntry": {
                    "type": "object",
                    "properties": {
                        "asset_id": {"type": "string"},
                        "business_date_year": {"type": "integer"},
                        "record_count": {"type": "integer"},
                        "average_close_price": {"type": "number"},
                        "min_close_price": {"type": "number"},
                        "max_close_price": {"type": "number"}
                    }
                },
                "PredictiveEntry": {
                    "type": "object",
                    "properties": {
                        "asset_id": {"type": "string"},
                        "predicted_next_close_price": {"type": "number"},
                        "calculation_time": {"type": "string"},
                        "training_points": {"type": "integer"},
                        "last_known_close": {"type": "number"},
                        "calculated_trend_slope": {"type": "number"},
                        "intercept": {"type": "number"},
                        "r_squared": {"type": "number"},
                        "last_business_date": {"type": "string"}
                    }
                },
                "AnalyticsRunResponse": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "descriptive_count": {"type": "integer"},
                        "predictive_count": {"type": "integer"},
                        "descriptive": {"type": "array", "items": {"$ref": "#/components/schemas/DescriptiveEntry"}},
                        "predictive": {"type": "array", "items": {"$ref": "#/components/schemas/PredictiveEntry"}}
                    }
                },
                "TimeSeriesMetrics": {
                    "type": "object",
                    "description": "Arbitrary metric key/value pairs for a single business_date",
                    "additionalProperties": True
                },
                "TimeSeriesRecord": {
                    "type": "object",
                    "properties": {
                        "asset_id": {"type": "string"},
                        "data_source_id": {"type": "string"},
                        "business_date": {"type": "string"},
                        "system_date": {"type": "string"},
                        "metrics": {"$ref": "#/components/schemas/TimeSeriesMetrics"},
                        "attributes": {"type": "array", "items": {"type": "string"}},
                        "provenance": {"type": "object", "additionalProperties": True},
                        "ingest_id": {"type": "string"},
                        "deleted": {"type": "boolean"}
                    },
                    "additionalProperties": True
                },
                "TimeSeriesDailyRecord": {
                    "type": "object",
                    "properties": {
                        "business_date": {"type": "string", "format": "date"},
                        "open_price": {"type": "number"},
                        "high_price": {"type": "number"},
                        "low_price": {"type": "number"},
                        "close_price": {"type": "number"},
                        "volume": {"type": "number"},
                        "current_price": {"type": "number"},
                        "adjusted_close_price": {"type": "number"},
                        "quoted_price": {"type": "number"}
                    }
                },
                "TimeSeriesDailyResponse": {
                    "type": "object",
                    "properties": {
                        "asset_id": {"type": "string"},
                        "data_source_id": {"type": "string"},
                        "daily": {"type": "array", "items": {"$ref": "#/components/schemas/TimeSeriesDailyRecord"}},
                        "count": {"type": "integer"}
                    }
                },
                "TimeSeriesRecordsResponse": {
                    "type": "object",
                    "properties": {
                        "asset_id": {"type": "string"},
                        "data_source_id": {"type": "string"},
                        "records": {"type": "array", "items": {"$ref": "#/components/schemas/TimeSeriesRecord"}},
                        "count": {"type": "integer"}
                    }
                },
                "MonthlyExportResponse": {
                    "type": "object",
                    "properties": {
                        "startBusinessDate": {"type": "string"},
                        "endBusinessDate": {"type": "string"},
                        "asset_count": {"type": "integer"},
                        "records": {"type": "array", "items": {"$ref": "#/components/schemas/TimeSeriesRecord"}}
                    }
                },
                "SupportedAssetsResponse": {
                    "type": "object",
                    "properties": {"supported": {"type": "array", "items": {"type": "string"}}}
                },
                "LLMResponse": {
                    "type": "object",
                    "properties": {"status": {"type": "string"}, "response": {"type": ["string", "object"]}, "asset_summary": {"type": "object", "additionalProperties": True}}
                }
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

