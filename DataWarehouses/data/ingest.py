import os
import requests
from datetime import datetime, timezone
from datetime import timedelta, date
from dotenv import load_dotenv

from db.database import insert_time_series_point

load_dotenv()

from db.database import timeseries_collection
NASDAQ_BASE_URL = "https://data.nasdaq.com/api/v3/datasets"

STOCK_ASSETS = {"AAPL", "MSFT", "GOOGL", "TSLA", "AMZN"}
BOND_ASSETS = {"US10Y", "US30Y", "CORP1"}
DERIVATIVE_ASSETS = {"OILFUT", "GOLDFUT", "SPXOPT"}
FX_ASSETS = {"EURUSD", "USDJPY", "GBPUSD"}
COMMODITY_ASSETS = {"CL=F", "GC=F", "NG=F"}
CRYPTO_ASSETS = {"BTCUSD", "ETHUSD", "LTCUSD"}
SUPPORTED_ASSETS = sorted(list(STOCK_ASSETS | BOND_ASSETS | DERIVATIVE_ASSETS | FX_ASSETS | COMMODITY_ASSETS | CRYPTO_ASSETS))

ASSET_PROVIDER_CONFIG = {
    "crypto": {
        "dataset_root": "BITFINEX",
        "source_identifier": "NASDAQ-DATA-LINK.QDL/BITFINEX",
        "display_name": "Nasdaq Data Link / Bitfinex",
        "description": "Nasdaq Data Link feed for cryptocurrency market data.",
        "asset_type": "cryptocurrency",
        "vendor_id": "NASDAQ",
        "vendor_name": "Nasdaq Data Link",
        "vendor_description": "Nasdaq provides market data through its Nasdaq Data Link API for financial instruments and exchange feeds.",
    },
    "equity": {
        "dataset_root": "EOD",
        "source_identifier": "NASDAQ-DATA-LINK.EOD",
        "display_name": "Nasdaq Data Link / EOD",
        "description": "Nasdaq Data Link end-of-day equity dataset for public stocks.",
        "asset_type": "equity",
        "vendor_id": "NASDAQ",
        "vendor_name": "Nasdaq Data Link",
        "vendor_description": "Nasdaq provides market data through its Nasdaq Data Link API for financial instruments and exchange feeds.",
    },
    "fixed_income": {
        "dataset_root": "WIKI",
        "source_identifier": "NASDAQ-DATA-LINK.WIKI",
        "display_name": "Nasdaq Data Link / Fixed Income",
        "description": "Nasdaq Data Link dataset for bond and fixed-income price history.",
        "asset_type": "fixed_income",
        "vendor_id": "NASDAQ",
        "vendor_name": "Nasdaq Data Link",
        "vendor_description": "Nasdaq provides market data through its Nasdaq Data Link API for financial instruments and exchange feeds.",
    },
    "derivative": {
        "dataset_root": "WIKI",
        "source_identifier": "NASDAQ-DATA-LINK.WIKI",
        "display_name": "Nasdaq Data Link / Derivatives",
        "description": "Nasdaq Data Link dataset for derivative contract data.",
        "asset_type": "derivative",
        "vendor_id": "NASDAQ",
        "vendor_name": "Nasdaq Data Link",
        "vendor_description": "Nasdaq provides market data through its Nasdaq Data Link API for financial instruments and exchange feeds.",
    },
    "forex": {
        "dataset_root": "WIKI",
        "source_identifier": "NASDAQ-DATA-LINK.WIKI",
        "display_name": "Nasdaq Data Link / Forex",
        "description": "Nasdaq Data Link dataset for foreign exchange contracts.",
        "asset_type": "forex",
        "vendor_id": "NASDAQ",
        "vendor_name": "Nasdaq Data Link",
        "vendor_description": "Nasdaq provides market data through its Nasdaq Data Link API for financial instruments and exchange feeds.",
    },
    "commodity": {
        "dataset_root": "WIKI",
        "source_identifier": "NASDAQ-DATA-LINK.WIKI",
        "display_name": "Nasdaq Data Link / Commodities",
        "description": "Nasdaq Data Link dataset for commodity market prices.",
        "asset_type": "commodity",
        "vendor_id": "NASDAQ",
        "vendor_name": "Nasdaq Data Link",
        "vendor_description": "Nasdaq provides market data through its Nasdaq Data Link API for financial instruments and exchange feeds.",
    },
}

ASSET_METADATA = {
    "BTCUSD": {"description": "Bitcoin digital currency", "region": "Global", "instrument_class": "cryptocurrency"},
    "ETHUSD": {"description": "Ethereum digital currency", "region": "Global", "instrument_class": "cryptocurrency"},
    "LTCUSD": {"description": "Litecoin digital currency", "region": "Global", "instrument_class": "cryptocurrency"},
    "AAPL": {"description": "Apple Inc. common stock", "region": "US", "instrument_class": "equity"},
    "MSFT": {"description": "Microsoft Corp. common stock", "region": "US", "instrument_class": "equity"},
    "GOOGL": {"description": "Alphabet Inc. Class A common stock", "region": "US", "instrument_class": "equity"},
    "TSLA": {"description": "Tesla Inc. common stock", "region": "US", "instrument_class": "equity"},
    "AMZN": {"description": "Amazon.com Inc. common stock", "region": "US", "instrument_class": "equity"},
    "US10Y": {"description": "10-year U.S. Treasury note", "region": "US", "instrument_class": "bond"},
    "US30Y": {"description": "30-year U.S. Treasury bond", "region": "US", "instrument_class": "bond"},
    "CORP1": {"description": "Corporate bond instrument", "region": "US", "instrument_class": "bond"},
    "OILFUT": {"description": "Crude oil futures contract", "region": "Global", "instrument_class": "derivative"},
    "GOLDFUT": {"description": "Gold futures contract", "region": "Global", "instrument_class": "derivative"},
    "SPXOPT": {"description": "S&P 500 index option contract", "region": "US", "instrument_class": "derivative"},
    "EURUSD": {"description": "Euro / U.S. dollar foreign exchange pair", "region": "Global", "instrument_class": "forex"},
    "USDJPY": {"description": "U.S. dollar / Japanese yen foreign exchange pair", "region": "Global", "instrument_class": "forex"},
    "GBPUSD": {"description": "British pound / U.S. dollar foreign exchange pair", "region": "Global", "instrument_class": "forex"},
    "CL=F": {"description": "Crude oil commodity future", "region": "Global", "instrument_class": "commodity"},
    "GC=F": {"description": "Gold commodity future", "region": "Global", "instrument_class": "commodity"},
    "NG=F": {"description": "Natural gas commodity future", "region": "Global", "instrument_class": "commodity"},
}

STANDARD_METRIC_MAPPING = {
    "open": "open_price",
    "high": "high_price",
    "low": "low_price",
    "close": "close_price",
    "volume": "volume",
    "adj_close": "adjusted_close_price",
    "adjusted_close": "adjusted_close_price",
    "quoted": "quoted_price",
    "ask_size": "ask_size",
    "last": "current_price",
}


def _normalize_metric_name(column_name):
    key = column_name.strip().lower().replace(" ", "_")
    return STANDARD_METRIC_MAPPING.get(key, key)


def _sanitize_query_parameters(params):
    if not isinstance(params, dict):
        return {}
    sanitized = {k: v for k, v in params.items() if k.lower() != "api_key"}
    return sanitized


def _build_provenance(url, query_params, row_index, column_names, page_number, page_row_index, next_cursor):
    return {
        "source_name": "Nasdaq Data Link",
        "source_url": url,
        "query_parameters": _sanitize_query_parameters(query_params),
        "page_number": page_number,
        "page_row_index": page_row_index,
        "row_index": row_index,
        "next_cursor_id": next_cursor,
        "columns": [c.lower() for c in column_names],
        "captured_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def _clean_metrics(columns, row):
    metrics = {}
    for index, column_name in enumerate(columns):
        if index == 0:
            continue
        metrics[_normalize_metric_name(column_name)] = row[index]

    if "close_price" in metrics:
        metrics.setdefault("current_price", metrics["close_price"])
        metrics.setdefault("adjusted_close_price", metrics["close_price"])
        metrics.setdefault("quoted_price", metrics["close_price"])
    if "open_price" in metrics and "quoted_price" not in metrics:
        metrics.setdefault("quoted_price", metrics["open_price"])

    return metrics


def _resolve_asset_metadata(asset_symbol, asset_class):
    normalized = asset_symbol.strip().upper()
    metadata = ASSET_METADATA.get(normalized, {})
    asset_type = ASSET_PROVIDER_CONFIG[asset_class]["asset_type"]
    return {
        "asset_type": asset_type,
        "description": metadata.get("description", f"{normalized} financial instrument."),
        "region": metadata.get("region", "Unknown"),
        "instrument_class": metadata.get("instrument_class", asset_class),
    }


def _resolve_asset_source(asset_symbol):
    normalized = asset_symbol.strip().upper()
    if normalized in CRYPTO_ASSETS:
        return "crypto"
    if normalized in STOCK_ASSETS:
        return "equity"
    if normalized in BOND_ASSETS:
        return "fixed_income"
    if normalized in DERIVATIVE_ASSETS:
        return "derivative"
    if normalized in FX_ASSETS:
        return "forex"
    if normalized in COMMODITY_ASSETS:
        return "commodity"
    if normalized.endswith("USD"):
        return "forex"
    return "equity"


def ingest_assets(asset_symbols=None, omit_fields=None):
    """Ingest a list of assets. Optionally provide `omit_fields` (list of metric names)
    which will be removed from metrics before storage.
    """
    if asset_symbols is None:
        asset_symbols = SUPPORTED_ASSETS
    assets = [str(asset).strip().upper() for asset in asset_symbols if str(asset).strip()]
    if not assets:
        assets = SUPPORTED_ASSETS

    if omit_fields is None:
        omit_fields = []

    results = []
    for asset_symbol in assets:
        try:
            fetch_and_ingest_nasdaq_data(asset_symbol, omit_fields=omit_fields)
            results.append({"asset": asset_symbol, "status": "ingested"})
        except Exception as exc:
            results.append({"asset": asset_symbol, "status": "error", "error": str(exc)})
    return results


def _build_source_metadata(columns, asset_symbol, source_config):
    normalized = ["business_date"] + [_normalize_metric_name(c) for c in columns if c.lower() != "date"]
    source_meta = {
        "display_name": f"{source_config['display_name']} ({asset_symbol})",
        "description": f"{source_config['description']} Ingested asset: {asset_symbol}.",
        "attributes": normalized,
    }
    if source_config.get("vendor_id"):
        source_meta["vendor_id"] = source_config["vendor_id"]
        source_meta["vendor_name"] = source_config["vendor_name"]
        source_meta["vendor_description"] = source_config.get("vendor_description")
    return source_meta


def fetch_and_ingest_nasdaq_data(asset_symbol, omit_fields=None):
    """
    Extracts market data from Nasdaq Data Link, transforms rows into canonical documents,
    and loads them into MongoDB with provenance and retry protection.
    """
    if not asset_symbol or not str(asset_symbol).strip():
        raise ValueError("Asset symbol is required for ingestion.")

    asset_symbol = str(asset_symbol).strip().upper()
    asset_class = _resolve_asset_source(asset_symbol)
    source_config = ASSET_PROVIDER_CONFIG[asset_class]
    asset_metadata = _resolve_asset_metadata(asset_symbol, asset_class)
    url = f"{NASDAQ_BASE_URL}/{source_config['dataset_root']}/{asset_symbol}.json"
    api_key = os.getenv("NASDAQ_API_KEY")
    params = {"rows": 100}
    if api_key and "YOUR_ACTUAL_NASDAQ" not in api_key:
        params["api_key"] = api_key

    source_identifier = source_config["source_identifier"]
    max_pages = 5
    current_page = 0
    cursor = None
    page_records = []

    try:
        while current_page < max_pages:
            page_params = {"rows": params["rows"]}
            if cursor:
                page_params["cursor_id"] = cursor
            if api_key and "YOUR_ACTUAL_NASDAQ" not in api_key:
                page_params["api_key"] = api_key

            response = requests.get(url, params=page_params, timeout=10)
            page_number = current_page + 1

            if response.status_code != 200:
                print(f"API returned status code {response.status_code} for {asset_symbol}. Using fallback data.")
                run_fallback_stream(asset_symbol, source_config)
                return

            json_payload = response.json()
            dataset_info = json_payload.get("dataset", {})
            columns = dataset_info.get("column_names", [])
            rows = dataset_info.get("data", [])

            if not rows:
                print(f"No rows returned for {asset_symbol}. Using fallback data.")
                run_fallback_stream(asset_symbol, source_config)
                return

            next_cursor = json_payload.get("datatable", {}).get("next_cursor_id") or json_payload.get("next_cursor_id")
            for page_row_index, row in enumerate(rows):
                page_records.append(
                    {
                        "row": row,
                        "page_number": page_number,
                        "page_row_index": page_row_index,
                        "page_params": page_params.copy(),
                        "next_cursor": next_cursor,
                    }
                )
                if len(page_records) >= 5:
                    break

            if len(page_records) >= 5 or not next_cursor:
                break

            cursor = next_cursor
            current_page += 1

        source_metadata = _build_source_metadata(columns, asset_symbol, source_config)
        bounded_records = page_records[:5]
        print(f"Processing {len(bounded_records)} recent market records for {asset_symbol}...")

        for row_index, record in enumerate(bounded_records):
            row = record["row"]
            market_date = row[0]
            metrics_map = _clean_metrics(columns, row)
            # Remove any omitted fields before persisting
            if omit_fields:
                for f in omit_fields:
                    metrics_map.pop(f, None)
                # also remove from source metadata attributes if present
                if source_metadata and source_metadata.get("attributes"):
                    source_metadata["attributes"] = [a for a in source_metadata["attributes"] if a not in omit_fields]
            provenance = _build_provenance(
                url,
                record["page_params"],
                row_index,
                columns,
                record["page_number"],
                record["page_row_index"],
                record["next_cursor"],
            )

            insert_time_series_point(
                asset_id=asset_symbol,
                source_id=source_identifier,
                business_date=market_date,
                metrics_dict=metrics_map,
                provenance=provenance,
                source_metadata=source_metadata,
                asset_metadata=asset_metadata,
            )

        print("Ingestion batch completed.")
    except Exception as error:
        print(f"Network request failed: {error}. Using fallback data for {asset_symbol}.")
        run_fallback_stream(asset_symbol, source_config, omit_fields=omit_fields)


def backfill_missing_dates(asset_symbol, start_date, end_date, source_identifier=None, omit_fields=None):
    """Backfill any missing business_date documents for `asset_symbol` in the inclusive range
    [start_date, end_date]. For each missing date, pick the nearest existing record (by business_date)
    and copy its metrics (applying `omit_fields`), then insert as a new time-series point with a
    provenance flag indicating it was backfilled.

    This keeps the DB consistent for UI/testing while avoiding synthetic extrapolation.
    """
    # Normalize dates to date objects
    def _to_date(d):
        if isinstance(d, str):
            return datetime.fromisoformat(d).date()
        if isinstance(d, datetime):
            return d.date()
        if isinstance(d, date):
            return d
        raise ValueError("Invalid date")

    s_dt = _to_date(start_date)
    e_dt = _to_date(end_date)
    if e_dt < s_dt:
        raise ValueError("end_date must be >= start_date")

    # build list of ISO date strings
    total_days = (e_dt - s_dt).days + 1
    wanted = [(s_dt + timedelta(days=i)).isoformat() for i in range(total_days)]

    # existing business_date values in range
    query = {"asset_id": asset_symbol, "business_date": {"$gte": wanted[0], "$lte": wanted[-1]}}
    if source_identifier:
        query["data_source_id"] = source_identifier

    existing = set(timeseries_collection.distinct("business_date", query))
    missing = [d for d in wanted if d not in existing]
    if not missing:
        return {"status": "noop", "message": "no missing dates", "missing": []}

    # fetch candidate docs for nearest selection (any source for asset)
    candidates = list(timeseries_collection.find({"asset_id": asset_symbol}).sort("business_date", 1))
    candidate_map = {c.get("business_date"): c for c in candidates}

    inserted = []
    for md in missing:
        # find nearest existing doc by min day difference
        nearest = None
        nearest_delta = None
        md_dt = datetime.fromisoformat(md).date()
        for bd, doc in candidate_map.items():
            try:
                bd_dt = datetime.fromisoformat(bd).date()
            except Exception:
                continue
            delta = abs((bd_dt - md_dt).days)
            if nearest is None or delta < nearest_delta:
                nearest = doc
                nearest_delta = delta

        # build metrics by copying nearest or using empty
        if nearest:
            metrics_copy = dict(nearest.get("metrics", {}))
            src_id = nearest.get("data_source_id")
        else:
            metrics_copy = {}
            src_id = None

        if omit_fields:
            for f in omit_fields:
                metrics_copy.pop(f, None)

        # derive common metrics if not present
        if "close_price" in metrics_copy:
            metrics_copy.setdefault("current_price", metrics_copy["close_price"])
            metrics_copy.setdefault("adjusted_close_price", metrics_copy["close_price"])
            metrics_copy.setdefault("quoted_price", metrics_copy["close_price"])
        if "open_price" in metrics_copy and "quoted_price" not in metrics_copy:
            metrics_copy.setdefault("quoted_price", metrics_copy["open_price"])

        final_source = source_identifier or src_id or ASSET_PROVIDER_CONFIG[_resolve_asset_source(asset_symbol)]["source_identifier"]

        provenance = {
            "source_name": "BACKFILL",
            "source_url": None,
            "query_parameters": {},
            "row_index": 0,
            "captured_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "note": "backfilled from nearest existing record",
        }

        insert_time_series_point(
            asset_id=asset_symbol,
            source_id=final_source,
            business_date=md,
            metrics_dict=metrics_copy,
            provenance=provenance,
            source_metadata={"attributes": list(nearest.get("attributes")) if nearest and nearest.get("attributes") else []},
            asset_metadata=_resolve_asset_metadata(asset_symbol, _resolve_asset_source(asset_symbol)),
        )

        inserted.append({"business_date": md, "metrics": metrics_copy, "source_id": final_source})

    return {"status": "ok", "inserted": inserted}


def run_fallback_stream(asset_symbol, source_config=None, omit_fields=None):
    """Fallback generator to keep your lab test running if external APIs throttle requests."""
    asset_symbol = str(asset_symbol).strip().upper()
    if source_config is None:
        asset_class = _resolve_asset_source(asset_symbol)
        source_config = ASSET_PROVIDER_CONFIG[asset_class]
    asset_class = _resolve_asset_source(asset_symbol)
    asset_metadata = _resolve_asset_metadata(asset_symbol, asset_class)

    source_identifier = source_config["source_identifier"]
    mock_historical_data = [
        {"date": "2026-06-05", "metrics": {"open_price": 98500.0, "close_price": 99200.0, "high_price": 99600.0, "low_price": 98100.0, "volume": 34500}},
        {"date": "2026-06-04", "metrics": {"open_price": 97200.0, "close_price": 98450.0, "high_price": 98900.0, "low_price": 96800.0, "volume": 29800}},
        {"date": "2026-06-03", "metrics": {"open_price": 96100.0, "close_price": 97150.0, "high_price": 97500.0, "low_price": 95400.0, "volume": 41200}},
    ]
    source_metadata = {
        "display_name": f"{source_config['display_name']} Fallback ({asset_symbol})",
        "description": f"Fallback sample data for the {source_config['display_name']} ingestion pipeline.",
        "attributes": ["business_date", "open_price", "high_price", "low_price", "close_price", "volume", "current_price", "adjusted_close_price", "quoted_price"],
        "vendor_id": source_config.get("vendor_id"),
        "vendor_name": source_config.get("vendor_name"),
        "vendor_description": source_config.get("vendor_description"),
    }
    for row_index, row in enumerate(mock_historical_data):
        provenance = {
            "source_name": f"{source_config['display_name']} Fallback",
            "source_url": None,
            "query_parameters": {},
            "row_index": row_index,
            "columns": ["open_price", "close_price", "high_price", "low_price", "volume"],
            "captured_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
        metrics = dict(row["metrics"])
        # Ensure common derived metrics are present for consistency with live ingestion
        if "close_price" in metrics:
            metrics.setdefault("current_price", metrics["close_price"])
            metrics.setdefault("adjusted_close_price", metrics["close_price"])
            metrics.setdefault("quoted_price", metrics["close_price"])
        if "open_price" in metrics and "quoted_price" not in metrics:
            metrics.setdefault("quoted_price", metrics["open_price"])
        if omit_fields:
            for f in omit_fields:
                metrics.pop(f, None)
            source_metadata["attributes"] = [a for a in source_metadata.get("attributes", []) if a not in (omit_fields or [])]

        insert_time_series_point(
            asset_id=asset_symbol,
            source_id=source_identifier,
            business_date=row["date"],
            metrics_dict=metrics,
            provenance=provenance,
            source_metadata=source_metadata,
            asset_metadata=asset_metadata,
        )
    print(f"Fallback ingestion completed for {asset_symbol}.")


if __name__ == "__main__":
    fetch_and_ingest_nasdaq_data("BTCUSD")