import os
from datetime import datetime, timedelta, date
from flask import Flask, request, jsonify, render_template, redirect

from app.llm_agent import LLMService
from app.mcp_tools import AVAILABLE_TOOLS, TOOL_DEFINITIONS, TOOL_SAMPLE_PARAMS, call_tool
from analytics.analytics import run_descriptive_analytics, run_predictive_analytics
from data.ingest import SUPPORTED_ASSETS, ingest_assets
from db.database import (
    assets_collection,
    db,
    mark_asset_deleted,
    query_asset_instrument_details,
    query_asset_lineage,
    query_common_indicators,
    query_latest_timeseries,
    query_latest_timeseries_for_assets,
    query_source_lineage,
    query_time_series_schema,
    query_vendor_assets,
    sources_collection,
    timeseries_collection,
)
from services.chat_service import ChatService
from bson import ObjectId


def _normalize_asset_list(value):
    if value is None:
        return None
    if isinstance(value, str):
        return [v.strip().upper() for v in value.replace(",", " ").split() if v.strip()]
    if isinstance(value, (list, tuple)):
        return [str(v).strip().upper() for v in value if v]
    return None


def _parse_iso_date(s):
    if not s:
        return None
    if isinstance(s, datetime):
        return s.date().isoformat()
    try:
        return str(s).split("T")[0]
    except Exception:
        return None


def _parse_bool(v):
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    sval = str(v).strip().lower()
    return sval in ("1", "true", "yes", "on")


def _sanitize_bson(obj):
    """Recursively sanitize BSON objects for JSON serialization.

    - remove top-level Mongo `_id` fields
    - convert `ObjectId` instances to strings
    - recurse into lists/dicts
    """
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "_id":
                continue
            out[k] = _sanitize_bson(v)
        return out
    if isinstance(obj, list):
        return [_sanitize_bson(x) for x in obj]
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, datetime):
        # Normalize datetimes to date-only ISO string for business_date consistency
        try:
            return obj.date().isoformat()
        except Exception:
            return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    return obj


def _fetch_latest_records_for_assets(asset_list):
    if not asset_list:
        return []
    try:
        rows = query_latest_timeseries_for_assets(asset_list)
        # sanitize BSON types (ObjectId) and remove raw _id before JSONifying
        sanitized = []
        for r in rows:
            sanitized.append(_sanitize_bson(r))
        return sanitized
    except Exception:
        return []


def register_routes(app: Flask):
    # Instantiate services using the app-level tool runner
    llm = LLMService(tool_runner=call_tool)
    chat_service = ChatService(tool_runner=call_tool)

    @app.route("/", methods=["GET"])
    def index():
        return redirect("/api/docs")

    @app.route("/run-pipeline", methods=["POST"])
    def run_pipeline():
        payload = request.get_json(silent=True) or {}
        assets = _normalize_asset_list(payload.get("assets") or payload.get("asset"))
        omit_fields = payload.get("omitFields") or payload.get("omit_fields") or []
        show_results = _parse_bool(payload.get("showResults") or payload.get("show_results"))

        if not assets:
            assets = SUPPORTED_ASSETS

        ingest_assets(assets, omit_fields=omit_fields)

        # run analytics (these functions persist results to DB as well)
        desc = run_descriptive_analytics()
        pred = run_predictive_analytics()

        # read persisted analytics collections as a fallback to ensure we return
        # the full analytics set (not limited to the `assets` request).
        try:
            totals_docs = list(db.get_collection("totals").find({}, {"_id": 0}))
        except Exception:
            totals_docs = []
        try:
            regression_docs = list(db.get_collection("regression_results").find({}, {"_id": 0}))
        except Exception:
            regression_docs = []

        totals_sanitized = [_sanitize_bson(d) for d in totals_docs]
        regression_sanitized = [_sanitize_bson(d) for d in regression_docs]

        descriptive_count = len(desc) if desc else len(totals_sanitized)
        predictive_count = len(pred) if pred else len(regression_sanitized)

        result = {
            "status": "success",
            "ingested": len(assets),
            "descriptive_count": descriptive_count,
            "predictive_count": predictive_count,
        }

        if show_results:
            # recent backend records for the requested assets
            result["recent_records"] = _fetch_latest_records_for_assets(assets)

            # Prefer returning the freshly computed `desc`/`pred` if available,
            # otherwise return the persisted collection contents (which cover all assets).
            if desc:
                result["descriptive"] = [_sanitize_bson(x) for x in desc]
            else:
                result["descriptive"] = totals_sanitized

            if pred:
                result["predictive"] = [_sanitize_bson(x) for x in pred]
            else:
                result["predictive"] = regression_sanitized

        return jsonify(result)

    @app.route("/run-ingest", methods=["POST"])  # human-friendly endpoint
    def run_ingest():
        payload = request.get_json(silent=True) or {}
        assets = _normalize_asset_list(payload.get("assets") or payload.get("asset"))
        omit_fields = payload.get("omitFields") or payload.get("omit_fields") or []
        show_results = _parse_bool(payload.get("showResults") or payload.get("show_results"))

        if not assets:
            assets = SUPPORTED_ASSETS

        ingest_assets(assets, omit_fields=omit_fields)
        response = {"status": "success", "ingested": len(assets)}
        if show_results:
            response["recent_records"] = _fetch_latest_records_for_assets(assets)
        return jsonify(response)

    @app.route("/api/ingestion/run", methods=["POST"])
    def api_run_ingest():
        return run_ingest()


    @app.route("/api/analytics/run", methods=["POST"])
    def api_run_analytics():
        """Trigger analytics runs. JSON body may include:
        - `descriptive` (bool) run descriptive analytics
        - `predictive` (bool) run predictive analytics
        - `async` (bool) run in background and return 202 immediately
        - `showResults` (bool) include results in response
        If neither `descriptive` nor `predictive` are provided, both are run.
        """
        payload = request.get_json(silent=True) or {}
        run_desc = payload.get("descriptive") if "descriptive" in payload else payload.get("run_descriptive")
        run_pred = payload.get("predictive") if "predictive" in payload else payload.get("run_predictive")

        # default to running both if not specified
        if run_desc is None and run_pred is None:
            run_desc = True
            run_pred = True

        async_run = _parse_bool(payload.get("async") or payload.get("background") or payload.get("async_run"))

        if async_run:
            import threading

            def _background():
                try:
                    if run_desc:
                        run_descriptive_analytics()
                    if run_pred:
                        run_predictive_analytics()
                except Exception:
                    pass

            threading.Thread(target=_background, daemon=True).start()
            return jsonify({"status": "started", "async": True}), 202

        # run synchronously
        desc_res = run_descriptive_analytics() if run_desc else []
        pred_res = run_predictive_analytics() if run_pred else []

        result = {
            "status": "completed",
            "descriptive_count": len(desc_res) if desc_res else 0,
            "predictive_count": len(pred_res) if pred_res else 0,
        }

        if _parse_bool(payload.get("showResults") or payload.get("show_results")):
            result["descriptive"] = desc_res
            result["predictive"] = pred_res

        return jsonify(result)

    @app.route("/api/supported-assets", methods=["GET"])
    def supported_assets():
        return jsonify({"supported": SUPPORTED_ASSETS})

    @app.route("/api/llm", methods=["POST"])
    def api_llm():
        payload = request.get_json(silent=True) or {}
        prompt = payload.get("prompt")
        asset_id = payload.get("assetId") or payload.get("asset_id")

        if prompt:
            if not llm.is_configured():
                return jsonify({"status": "error", "message": "LLM not configured"}), 503
            out = llm.generate_with_tools(prompt)
            return jsonify({"status": "success", "response": out})

        if asset_id:
            asset_summary = chat_service.summarize_asset_performance(asset_id, payload.get("startBusinessDate"), payload.get("endBusinessDate"))
            explanation = llm.explain_asset(asset_id, payload.get("startBusinessDate"), payload.get("endBusinessDate"), asset_summary)
            return jsonify({"status": "success", "response": explanation, "asset_summary": asset_summary})

        return jsonify({"status": "error", "message": "No prompt or assetId provided"}), 400

    @app.route("/api/assets", methods=["GET"])
    def api_list_assets():
        try:
            limit = int(request.args.get("limit", 100))
        except Exception:
            limit = 100
        docs = list(assets_collection.find({}).limit(limit))
        for d in docs:
            d.pop("_id", None)
        return jsonify({"assets": docs})

    @app.route("/api/assets/<asset_id>", methods=["GET"])
    def api_get_asset(asset_id):
        asset_id_u = str(asset_id).strip().upper()
        asset_doc = assets_collection.find_one({"asset_id": asset_id_u})
        if not asset_doc:
            return jsonify({"status": "error", "message": "Asset not found"}), 404
        sanitized = _sanitize_bson(asset_doc)
        return jsonify({"asset_id": asset_id_u, "asset": sanitized})

    @app.route("/api/assets/<asset_id>/details", methods=["GET"])
    def api_asset_details(asset_id):
        asset_id_u = str(asset_id).strip().upper()
        asset_doc = assets_collection.find_one({"asset_id": asset_id_u})
        details = {"asset": asset_doc}

        # linked data sources
        linked = list(sources_collection.find({"data_source_id": {"$exists": True}}))
        for l in linked:
            l.pop("_id", None)

        start = _parse_iso_date(request.args.get("startBusinessDate"))
        end = _parse_iso_date(request.args.get("endBusinessDate"))

        historical = query_latest_timeseries(asset_id_u, start_date=start, end_date=end)
        for h in historical:
            h.pop("_id", None)

        return jsonify({"asset_id": asset_id_u, "details": details, "linked_data_sources": linked, "historical_records": historical})

    @app.route("/api/time-series", methods=["GET"])
    def api_time_series():
        asset_id = request.args.get("assetId") or request.args.get("asset_id")
        data_source_id = request.args.get("dataSourceId") or request.args.get("data_source_id")
        if not asset_id:
            return jsonify({"status": "error", "message": "assetId query parameter is required"}), 400

        start = _parse_iso_date(request.args.get("startBusinessDate"))
        end = _parse_iso_date(request.args.get("endBusinessDate"))
        try:
            limit = int(request.args.get("limit", 100))
        except Exception:
            limit = 100
        include_deleted = _parse_bool(request.args.get("includeDeleted") or request.args.get("include_deleted"))

        rows = query_latest_timeseries(asset_id, source_id=data_source_id, start_date=start, end_date=end, limit=limit, include_deleted=include_deleted)
        sanitized = [_sanitize_bson(r) for r in rows]

        # If both start and end provided, return one entry per day in the inclusive range
        if start and end:
            try:
                start_dt = datetime.fromisoformat(start).date()
                end_dt = datetime.fromisoformat(end).date()
            except Exception:
                return jsonify({"status": "error", "message": "Invalid startBusinessDate or endBusinessDate format (expected YYYY-MM-DD)"}), 400

            if end_dt < start_dt:
                return jsonify({"status": "error", "message": "endBusinessDate must be on or after startBusinessDate"}), 400

            # Build a lookup by business_date
            lookup = {r.get("business_date"): r for r in sanitized}
            daily = []
            cur = start_dt

            # Metrics we expose per day (in requested order)
            metrics_keys = [
                "open_price",
                "high_price",
                "low_price",
                "close_price",
                "volume",
                "current_price",
                "adjusted_close_price",
                "quoted_price",
            ]

            while cur <= end_dt:
                key = cur.isoformat()
                rec = lookup.get(key)
                if rec and isinstance(rec, dict):
                    rec_metrics = rec.get("metrics", {}) or {}
                    row = {}
                    for k in metrics_keys:
                        val = rec_metrics.get(k)
                        # derive common fallbacks when not present
                        if val is None:
                            if k in ("current_price", "adjusted_close_price", "quoted_price") and rec_metrics.get("close_price") is not None:
                                val = rec_metrics.get("close_price")
                        row[k] = val
                else:
                    row = {k: None for k in metrics_keys}

                # Always include business_date in the returned row
                row_out = {"business_date": key}
                row_out.update(row)
                daily.append(row_out)
                cur = cur + timedelta(days=1)

            return jsonify({"asset_id": asset_id, "data_source_id": data_source_id, "daily": daily, "count": len(daily)})

        return jsonify({"asset_id": asset_id, "data_source_id": data_source_id, "records": sanitized, "count": len(sanitized)})

    @app.route("/api/export/monthly-data", methods=["GET"])
    def api_export_monthly_data():
        end = _parse_iso_date(request.args.get("endBusinessDate"))
        try:
            days = int(request.args.get("days", 30))
        except Exception:
            days = 30
        if not end:
            return jsonify({"status": "error", "message": "endBusinessDate required"}), 400
        end_dt = datetime.fromisoformat(end)
        start_dt = (end_dt - timedelta(days=days - 1)).date()
        start = start_dt.isoformat()

        records = list(timeseries_collection.find({"business_date": {"$gte": start, "$lte": end}}))
        for r in records:
            r.pop("_id", None)

        asset_count = len({r.get("asset_id") for r in records})
        return jsonify({"startBusinessDate": start, "endBusinessDate": end, "asset_count": asset_count, "records": records})
