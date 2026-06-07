import json
from datetime import datetime
from db.database import assets_collection, query_common_indicators, sources_collection, timeseries_collection, db

# Tool descriptions for the assistant
AVAILABLE_TOOLS = {
    "list_assets": "Returns a paginated list of active assets and metadata. Do not provide investment advice.",
    "get_asset_details": "Returns a specific asset's complete temporal history and metadata, ordered by newest system date.",
    "list_data_sources": "Returns a catalog of data sources and lineage metadata for the platform.",
    "get_data_source_details": "Returns discovery details and attribute schema for a specific data source provider.",
    "get_time_series_data": "Returns bounded time-series records for a single asset and source, with date filtering and newest variant selection.",
    "get_time_series_schema": "Returns the available time-series attribute schema and vendor/source mappings for a given asset or provider.",
    "get_instrument_indicators": "Returns recent common financial indicators from MongoDB for supported instruments and sources.",
    "get_asset_indicators": "Returns financial instrument indicator coverage and vendor links for a specific asset.",
    "get_vendor_assets": "Returns all assets associated with a specific vendor based on known data sources.",
    "get_analytics_summary": "Returns yearly descriptive analytics summaries from the totals collection. No financial advice.",
    "get_market_predictions": "Returns predictive regression results from the regression_results collection. Only model outputs, not advice.",
    "list_vendors": "Returns a list of financial data vendors known to the platform based on registered data sources.",
    "get_vendor_details": "Returns a vendor's details and associated data sources for a specified vendor ID.",
    "get_asset_analytics": "Returns both descriptive and predictive analytics for a specific asset, if available.",
}

TOOL_DEFINITIONS = {
    "list_assets": {
        "description": AVAILABLE_TOOLS["list_assets"],
        "params": {},
    },
    "get_asset_details": {
        "description": AVAILABLE_TOOLS["get_asset_details"],
        "params": {"assetId": "string"},
    },
    "list_data_sources": {
        "description": AVAILABLE_TOOLS["list_data_sources"],
        "params": {},
    },
    "get_data_source_details": {
        "description": AVAILABLE_TOOLS["get_data_source_details"],
        "params": {"dataSourceId": "string"},
    },
    "get_time_series_data": {
        "description": AVAILABLE_TOOLS["get_time_series_data"],
        "params": {
            "assetId": "string",
            "dataSourceId": "string",
            "startBusinessDate": "YYYY-MM-DD",
            "endBusinessDate": "YYYY-MM-DD",
            "asOfSystemDate": "YYYY-MM-DDTHH:MM:SSZ",
        },
    },
    "get_time_series_schema": {
        "description": AVAILABLE_TOOLS["get_time_series_schema"],
        "params": {
            "assetId": "string",
            "dataSourceId": "string",
        },
    },
    "get_instrument_indicators": {
        "description": AVAILABLE_TOOLS["get_instrument_indicators"],
        "params": {},
    },
    "get_asset_indicators": {
        "description": AVAILABLE_TOOLS["get_asset_indicators"],
        "params": {"assetId": "string"},
    },
    "get_vendor_assets": {
        "description": AVAILABLE_TOOLS["get_vendor_assets"],
        "params": {"vendorId": "string"},
    },
    "get_analytics_summary": {
        "description": AVAILABLE_TOOLS["get_analytics_summary"],
        "params": {},
    },
    "get_market_predictions": {
        "description": AVAILABLE_TOOLS["get_market_predictions"],
        "params": {},
    },
    "list_vendors": {
        "description": AVAILABLE_TOOLS["list_vendors"],
        "params": {},
    },
    "get_vendor_details": {
        "description": AVAILABLE_TOOLS["get_vendor_details"],
        "params": {"vendorId": "string"},
    },
    "get_asset_analytics": {
        "description": AVAILABLE_TOOLS["get_asset_analytics"],
        "params": {"assetId": "string"},
    },
    "compare_assets": {
        "description": "Compare two assets over a date range and return summary stats and percent changes.",
        "params": {"assetIdA": "string", "assetIdB": "string", "dataSourceId": "string", "startBusinessDate": "YYYY-MM-DD", "endBusinessDate": "YYYY-MM-DD"},
    },
}

TOOL_SAMPLE_PARAMS = {
    "list_assets": {},
    "get_asset_details": {"assetId": "ETHUSD"},
    "list_data_sources": {},
    "get_data_source_details": {"dataSourceId": "NASDAQ-DATA-LINK.QDL/BITFINEX"},
    "get_time_series_data": {"assetId": "ETHUSD", "dataSourceId": "NASDAQ-DATA-LINK.QDL/BITFINEX", "startBusinessDate": "2026-01-01", "endBusinessDate": "2026-01-10", "asOfSystemDate": "2026-06-06"},
    "get_time_series_schema": {"assetId": "ETHUSD", "dataSourceId": "NASDAQ-DATA-LINK.QDL/BITFINEX"},
    "get_analytics_summary": {},
    "get_market_predictions": {},
    "list_vendors": {},
    "get_vendor_details": {"vendorId": "NASDAQ"},
    "get_asset_indicators": {"assetId": "BTCUSD"},
    "get_vendor_assets": {"vendorId": "NASDAQ"},
    "get_asset_analytics": {"assetId": "ETHUSD"},
}

TOOL_SAMPLE_PARAMS["compare_assets"] = {"assetIdA": "BTCUSD", "assetIdB": "ETHUSD", "startBusinessDate": "2026-01-01", "endBusinessDate": "2026-06-01"}


def _clean_documents(records):
    """Return a JSON-serializable copy of records, converting ObjectId and datetime values."""
    def _serialize_value(v):
        if isinstance(v, datetime):
            return v.replace(microsecond=0).isoformat() + "Z"
        if isinstance(v, dict):
            return {k: _serialize_value(val) for k, val in v.items()}
        if isinstance(v, list):
            return [_serialize_value(x) for x in v]
        return v

    out = []
    for record in records:
        if isinstance(record, dict):
            rec = record.copy()
            rec["_id"] = str(rec.get("_id"))
            out.append(_serialize_value(rec))
        else:
            out.append(_serialize_value(record))
    return out


def _parse_iso_date(date_str):
    if not isinstance(date_str, str):
        return None
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        return None


def _validate_tool_params(tool_name, params):
    if tool_name not in TOOL_DEFINITIONS:
        return f"Tool '{tool_name}' is not supported."

    schema = TOOL_DEFINITIONS[tool_name]["params"]
    if not isinstance(params, dict):
        return "Tool parameters must be an object."

    missing = [key for key in [k for k in schema if schema[k] == 'string'] if key not in params]
    if missing:
        return f"Missing required parameters: {', '.join(missing)}."

    invalid_keys = [key for key in params if key not in schema]
    if invalid_keys:
        return f"Unexpected parameter(s): {', '.join(invalid_keys)}."

    for key, value in params.items():
        if key in {"startBusinessDate", "endBusinessDate", "asOfSystemDate"} and value is not None:
            if _parse_iso_date(value) is None:
                return f"Invalid ISO date value for {key}: {value}."

    start = params.get("startBusinessDate")
    end = params.get("endBusinessDate")
    if start and end:
        start_date = _parse_iso_date(start)
        end_date = _parse_iso_date(end)
        if start_date and end_date and start_date > end_date:
            return "startBusinessDate must be earlier than or equal to endBusinessDate."

    return None


def call_tool(tool_name, params=None):
    params = params or {}
    validation_error = _validate_tool_params(tool_name, params)
    if validation_error:
        return {"status": "error", "message": validation_error}

    if tool_name == "list_assets":
        records = list(assets_collection.find({}, {"_id": 0}).sort("asset_id", 1))
        return {"status": "success", "data": {"assets": records, "total_count": len(records)}}

    elif tool_name == "get_asset_details":
        asset_id = params.get("assetId")
        if not asset_id:
            return {"status": "error", "message": "Missing required parameter: assetId."}

        asset_info = assets_collection.find_one({"asset_id": asset_id}, {"_id": 0})
        if not asset_info:
            return {"status": "error", "message": f"Asset {asset_id} not found."}

        records = list(timeseries_collection.find({"asset_id": asset_id}).sort("system_date", -1))
        return {
            "status": "success",
            "data": {
                "asset": asset_info,
                "history": _clean_documents(records),
            },
        }

    elif tool_name == "list_data_sources":
        records = list(sources_collection.find({}, {"_id": 0}).sort("data_source_id", 1))
        return {"status": "success", "data": {"data_sources": records, "total_count": len(records)}}

    elif tool_name == "get_data_source_details":
        data_source_id = params.get("dataSourceId")
        if not data_source_id:
            return {"status": "error", "message": "Missing required parameter: dataSourceId."}

        record = sources_collection.find_one({"data_source_id": data_source_id}, {"_id": 0})
        if not record:
            return {"status": "error", "message": f"Data source {data_source_id} not found."}

        return {"status": "success", "data": {"data_source": record}}

    elif tool_name == "list_vendors":
        pipeline = [
            {"$match": {"vendor_id": {"$ne": None}}},
            {"$group": {
                "_id": {
                    "vendor_id": "$vendor_id",
                    "vendor_name": "$vendor_name",
                    "vendor_description": "$vendor_description",
                }
            }},
            {"$replaceRoot": {"newRoot": {
                "vendor_id": "$_id.vendor_id",
                "vendor_name": "$_id.vendor_name",
                "vendor_description": "$_id.vendor_description",
            } }},
            {"$sort": {"vendor_name": 1}},
        ]
        vendors = list(sources_collection.aggregate(pipeline))
        return {"status": "success", "data": {"vendors": vendors}}

    elif tool_name == "get_vendor_details":
        vendor_id = params.get("vendorId")
        if not vendor_id:
            return {"status": "error", "message": "Missing required parameter: vendorId."}

        sources = list(sources_collection.find({"vendor_id": vendor_id}, {"_id": 0}).sort("data_source_id", 1))
        if not sources:
            return {"status": "error", "message": f"Vendor {vendor_id} not found."}

        vendor_info = {
            "vendor_id": vendor_id,
            "vendor_name": sources[0].get("vendor_name"),
            "vendor_description": sources[0].get("vendor_description"),
            "data_sources": sources,
        }
        return {"status": "success", "data": {"vendor": vendor_info}}

    elif tool_name == "get_time_series_data":
        asset_id = params.get("assetId")
        data_source_id = params.get("dataSourceId")
        start_date = params.get("startBusinessDate")
        end_date = params.get("endBusinessDate")
        if not asset_id or not data_source_id:
            return {"status": "error", "message": "Missing required parameters: assetId and dataSourceId."}

        query = {"asset_id": asset_id, "data_source_id": data_source_id}
        if start_date:
            query["business_date"] = {"$gte": start_date}
        if end_date:
            query.setdefault("business_date", {})["$lt"] = end_date

        pipeline = [
            {"$match": query},
            {"$sort": {"business_date": -1, "system_date": -1}},
            {"$group": {"_id": "$business_date", "doc": {"$first": "$$ROOT"}}},
            {"$replaceRoot": {"newRoot": "$doc"}},
            {"$sort": {"business_date": -1}},
            {"$limit": 100},
        ]

        records = list(timeseries_collection.aggregate(pipeline))
        return {"status": "success", "data": {"asset_id": asset_id, "data_source_id": data_source_id, "records": _clean_documents(records)}}

    elif tool_name == "get_instrument_indicators":
        records = query_common_indicators(limit=100)
        return {"status": "success", "data": {"indicators": _clean_documents(records)}}

    elif tool_name == "get_time_series_schema":
        asset_id = params.get("assetId")
        data_source_id = params.get("dataSourceId")
        try:
            from db.database import query_time_series_schema
        except Exception:
            return {"status": "error", "message": "Query helper unavailable."}
        schema_records = query_time_series_schema(asset_id=asset_id, source_id=data_source_id)
        return {"status": "success", "data": {"schemas": schema_records}}

    elif tool_name == "get_asset_indicators":
        asset_id = params.get("assetId")
        if not asset_id:
            return {"status": "error", "message": "Missing required parameter: assetId."}
        try:
            from db.database import query_asset_instrument_details
        except Exception:
            return {"status": "error", "message": "Query helper unavailable."}
        details = query_asset_instrument_details(asset_id)
        if not details:
            return {"status": "error", "message": f"Asset {asset_id} not found."}
        return {"status": "success", "data": details}

    elif tool_name == "get_vendor_assets":
        vendor_id = params.get("vendorId")
        if not vendor_id:
            return {"status": "error", "message": "Missing required parameter: vendorId."}
        try:
            from db.database import query_vendor_assets
        except Exception:
            return {"status": "error", "message": "Query helper unavailable."}
        assets = query_vendor_assets(vendor_id)
        return {"status": "success", "data": {"vendor_id": vendor_id, "assets": assets}}

    elif tool_name == "get_analytics_summary":
        totals = list(db["totals"].find({}, {"_id": 0}).sort([("asset_id", 1), ("business_date_year", 1)]))
        return {"status": "success", "data": {"yearly_summaries": totals}}

    elif tool_name == "get_market_predictions":
        predictions = list(db["regression_results"].find({}, {"_id": 0}).sort("asset_id", 1))
        return {"status": "success", "data": {"predictive_trends": predictions}}

    elif tool_name == "get_asset_analytics":
        asset_id = params.get("assetId")
        if not asset_id:
            return {"status": "error", "message": "Missing required parameter: assetId."}

        totals = list(db["totals"].find({"asset_id": asset_id}, {"_id": 0}).sort("business_date_year", 1))
        predictions = list(db["regression_results"].find({"asset_id": asset_id}, {"_id": 0}))
        return {
            "status": "success",
            "data": {
                "asset_id": asset_id,
                "yearly_summaries": totals,
                "predictions": predictions,
            },
        }

    elif tool_name == "compare_assets":
        asset_a = params.get("assetIdA")
        asset_b = params.get("assetIdB")
        if not asset_a or not asset_b:
            return {"status": "error", "message": "Missing required parameters: assetIdA and assetIdB."}

        # Optional filters
        source_id = params.get("dataSourceId")
        start = params.get("startBusinessDate")
        end = params.get("endBusinessDate")

        def _fetch_closes(asset):
            query = {"asset_id": asset}
            if source_id:
                query["data_source_id"] = source_id
            if start:
                query["business_date"] = {"$gte": start}
            if end:
                query.setdefault("business_date", {})["$lt"] = end
            cursor = timeseries_collection.find(query, {"_id": 0, "business_date": 1, "metrics.close": 1}).sort("business_date", 1)
            return [r for r in cursor]

        recs_a = _fetch_closes(asset_a)
        recs_b = _fetch_closes(asset_b)

        def _stats(recs):
            closes = [r.get("metrics", {}).get("close") for r in recs if r.get("metrics") and r.get("metrics").get("close") is not None]
            if not closes:
                return {"count": 0}
            first = closes[0]
            last = closes[-1]
            avg = sum(closes) / len(closes)
            pct_change = ((last - first) / first) * 100 if first != 0 else None
            # volatility: std dev of daily returns
            returns = []
            for i in range(1, len(closes)):
                prev = closes[i - 1]
                cur = closes[i]
                if prev != 0:
                    returns.append((cur - prev) / prev)
            vol = None
            if len(returns) >= 1:
                import math
                mean_r = sum(returns) / len(returns)
                if len(returns) > 1:
                    var = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
                else:
                    var = 0.0
                vol = math.sqrt(var)

            return {
                "count": len(closes),
                "first": first,
                "last": last,
                "average": round(avg, 4),
                "percent_change": round(pct_change, 4) if pct_change is not None else None,
                "volatility": round(vol, 6) if vol is not None else None,
            }

        stats_a = _stats(recs_a)
        stats_b = _stats(recs_b)

        # compute correlation on overlapping dates
        map_a = {r.get("business_date"): r.get("metrics", {}).get("close") for r in recs_a if r.get("metrics")}
        map_b = {r.get("business_date"): r.get("metrics", {}).get("close") for r in recs_b if r.get("metrics")}
        common_dates = sorted([d for d in map_a.keys() if d in map_b])
        correlation = None
        if len(common_dates) >= 2:
            xs = [map_a[d] for d in common_dates]
            ys = [map_b[d] for d in common_dates]
            import math
            mean_x = sum(xs) / len(xs)
            mean_y = sum(ys) / len(ys)
            num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
            denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
            denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
            denom = denom_x * denom_y
            if denom != 0:
                correlation = num / denom

        summary = {
            "assetA": asset_a,
            "assetB": asset_b,
            "statsA": stats_a,
            "statsB": stats_b,
            "correlation": round(correlation, 6) if correlation is not None else None,
            "overlap_days": len(common_dates),
        }

        return {"status": "success", "data": summary, "summary": f"Compared {asset_a} vs {asset_b}"}

    else:
        return {"status": "error", "message": f"Tool '{tool_name}' not found."}


def run_interactive_mcp_demo():
    print("Model Context Protocol server starting")
    print("The following tools are available:")
    for name, desc in AVAILABLE_TOOLS.items():
        print(f"Tool Name: {name}\n   Description: {desc}\n")

    print("Start tool simulation")

    while True:
        print("\nAvailable actions:")
        print("1. list_assets")
        print("2. get_asset_details")
        print("3. list_data_sources")
        print("4. get_data_source_details")
        print("5. get_time_series_data")
        print("6. get_time_series_schema")
        print("7. get_instrument_indicators")
        print("8. get_asset_indicators")
        print("9. get_vendor_assets")
        print("10. get_analytics_summary")
        print("11. get_market_predictions")
        print("12. get_asset_analytics")
        print("13. Exit")

        choice = input("\nSelect a tool number to simulate execution: ").strip()

        if choice == "1":
            response = call_tool("list_assets")
        elif choice == "2":
            asset_id = input("Enter assetId: ").strip()
            response = call_tool("get_asset_details", {"assetId": asset_id})
        elif choice == "3":
            response = call_tool("list_data_sources")
        elif choice == "4":
            source_id = input("Enter dataSourceId: ").strip()
            response = call_tool("get_data_source_details", {"dataSourceId": source_id})
        elif choice == "5":
            asset_id = input("Enter assetId: ").strip()
            source_id = input("Enter dataSourceId: ").strip()
            start_date = input("Enter startBusinessDate (YYYY-MM-DD or blank): ").strip() or None
            end_date = input("Enter endBusinessDate (YYYY-MM-DD or blank): ").strip() or None
            response = call_tool(
                "get_time_series_data",
                {"assetId": asset_id, "dataSourceId": source_id, "startBusinessDate": start_date, "endBusinessDate": end_date},
            )
        elif choice == "6":
            asset_id = input("Enter assetId (optional): ").strip() or None
            source_id = input("Enter dataSourceId (optional): ").strip() or None
            response = call_tool("get_time_series_schema", {"assetId": asset_id, "dataSourceId": source_id})
        elif choice == "7":
            response = call_tool("get_instrument_indicators")
        elif choice == "8":
            asset_id = input("Enter assetId: ").strip()
            response = call_tool("get_asset_indicators", {"assetId": asset_id})
        elif choice == "9":
            vendor_id = input("Enter vendorId: ").strip()
            response = call_tool("get_vendor_assets", {"vendorId": vendor_id})
        elif choice == "10":
            response = call_tool("get_analytics_summary")
        elif choice == "11":
            response = call_tool("get_market_predictions")
        elif choice == "12":
            asset_id = input("Enter assetId: ").strip()
            response = call_tool("get_asset_analytics", {"assetId": asset_id})
        elif choice == "13":
            print("\nExiting tool simulator.")
            break
        else:
            print("Invalid choice. Use a number from 1 to 12.")
            continue

        print(f"\n[MCP Outbound Response] ->\n{json.dumps(response, indent=2)}")


if __name__ == "__main__":
    run_interactive_mcp_demo()