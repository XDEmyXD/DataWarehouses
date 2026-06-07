import hashlib
import json
import os
from datetime import datetime, timezone
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from dotenv import load_dotenv

# Load our secret keys
load_dotenv()

# Connect to MongoDB on your computer
client = MongoClient(os.getenv("MONGO_URI"))

# Create a database named 'acme_dw'
db = client["acme_dw"]

# Create our 3 main collections (our filing drawers)
assets_collection = db["assets"]
sources_collection = db["data_sources"]
timeseries_collection = db["time_series_data"]

# Ensure key operational indexes for temporal lookup and idempotent ingestion
timeseries_collection.create_index([
    ("asset_id", 1),
    ("data_source_id", 1),
    ("business_date", 1),
    ("system_date", -1)
])
timeseries_collection.create_index([("ingest_id", 1)], unique=True, sparse=True)
assets_collection.create_index([("asset_id", 1)], unique=True, sparse=True)
sources_collection.create_index([("data_source_id", 1)], unique=True, sparse=True)


def _utc_now():
    """Return a UTC naive datetime (no microseconds) suitable for MongoDB storage."""
    return datetime.utcnow().replace(microsecond=0)

COMMON_FINANCIAL_INDICATORS = [
    "current_price",
    "open_price",
    "close_price",
    "adjusted_close_price",
    "quoted_price",
    "ask_size",
    "volume",
]


def query_common_indicators(
    asset_id=None,
    source_id=None,
    start_date=None,
    end_date=None,
    as_of_system_date=None,
    limit=100,
    include_deleted=False,
):
    query = {}
    if asset_id:
        query["asset_id"] = asset_id
    if source_id:
        query["data_source_id"] = source_id
    if start_date:
        query["business_date"] = {"$gte": start_date}
    if end_date:
        query.setdefault("business_date", {})["$lte"] = end_date
    if as_of_system_date:
        # Normalize as-of value to a datetime (accepts datetime or ISO string)
        try:
            from datetime import timezone as _tz  # local import for safety
        except Exception:
            _tz = None
        if isinstance(as_of_system_date, datetime):
            dt_as_of = as_of_system_date.replace(microsecond=0)
            if dt_as_of.tzinfo is not None:
                dt_as_of = dt_as_of.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            # handle trailing Z and plain ISO strings
            s = str(as_of_system_date).strip()
            if s.endswith("Z"):
                s = s[:-1]
            try:
                dt_as_of = datetime.fromisoformat(s)
                if dt_as_of.tzinfo is not None:
                    dt_as_of = dt_as_of.astimezone(timezone.utc).replace(tzinfo=None)
                dt_as_of = dt_as_of.replace(microsecond=0)
            except Exception:
                dt_as_of = None
        if dt_as_of:
            query["system_date"] = {"$lte": dt_as_of}
    if not include_deleted:
        query["deleted"] = {"$ne": True}

    project = {"asset_id": 1, "data_source_id": 1, "business_date": 1, "system_date": 1}
    for metric in COMMON_FINANCIAL_INDICATORS:
        project[f"metrics.{metric}"] = 1

    pipeline = [
        {"$match": query},
        {"$sort": {"asset_id": 1, "data_source_id": 1, "business_date": -1, "system_date": -1}},
        {
            "$group": {
                "_id": {
                    "asset_id": "$asset_id",
                    "data_source_id": "$data_source_id",
                    "business_date": "$business_date",
                },
                "doc": {"$first": "$$ROOT"},
            }
        },
        {"$replaceRoot": {"newRoot": "$doc"}},
        {"$project": project},
        {
            "$lookup": {
                "from": "data_sources",
                "localField": "data_source_id",
                "foreignField": "data_source_id",
                "as": "source_info",
            }
        },
        {"$unwind": {"path": "$source_info", "preserveNullAndEmptyArrays": True}},
        {"$addFields": {
            "vendor_id": "$source_info.vendor_id",
            "vendor_name": "$source_info.vendor_name",
            "vendor_description": "$source_info.vendor_description",
        }},
        {"$project": {"source_info": 0}},
        {"$sort": {"asset_id": 1, "data_source_id": 1, "business_date": -1}},
        {"$limit": limit},
    ]
    return list(timeseries_collection.aggregate(pipeline))


def _generate_ingest_id(asset_id, source_id, business_date, metrics_dict, provenance):
    payload = {
        "asset_id": asset_id,
        "data_source_id": source_id,
        "business_date": business_date,
        "metrics": metrics_dict,
        "provenance": provenance,
    }
    normalized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class WarehouseRepository:
    def save(self, entity):
        raise NotImplementedError

    def delete(self, entity):
        raise NotImplementedError

    def delete_all(self, partition_key):
        raise NotImplementedError

    def find_latest(self, partition_key):
        raise NotImplementedError

    def find_all(self, partition_key):
        raise NotImplementedError


class MongoTimeSeriesRepository(WarehouseRepository):
    def __init__(self, collection):
        self.collection = collection

    def save(self, entity):
        if "ingest_id" not in entity:
            raise ValueError("Entity must include an ingest_id for idempotent storage.")

        insert_doc = entity.copy()
        try:
            result = self.collection.update_one(
                {"ingest_id": entity["ingest_id"]},
                {"$setOnInsert": insert_doc},
                upsert=True,
            )
            return result.upserted_id
        except DuplicateKeyError:
            return None

    def delete(self, entity):
        marker = {
            "asset_id": entity.get("asset_id"),
            "data_source_id": entity.get("data_source_id"),
            "business_date": entity.get("business_date"),
            "system_date": _utc_now(),
            "deleted": True,
            "metrics": {},
            "provenance": {
                "reason": "soft delete marker",
                "source": "warehouse repository",
            },
        }
        self.collection.insert_one(marker)

    def delete_all(self, partition_key):
        marker = {
            "asset_id": partition_key.get("asset_id"),
            "data_source_id": partition_key.get("data_source_id"),
            "business_date": partition_key.get("business_date"),
            "system_date": _utc_now(),
            "deleted": True,
            "metrics": {},
            "provenance": {
                "reason": "bulk soft delete marker",
                "source": "warehouse repository",
            },
        }
        self.collection.insert_one(marker)

    def find_latest(self, partition_key):
        query = {
            "asset_id": partition_key.get("asset_id"),
            "data_source_id": partition_key.get("data_source_id"),
        }
        return self.collection.find_one(query, sort=[("system_date", -1)])

    def find_all(self, partition_key):
        query = {
            "asset_id": partition_key.get("asset_id"),
            "data_source_id": partition_key.get("data_source_id"),
        }
        return list(self.collection.find(query).sort("system_date", -1))


time_series_repository = MongoTimeSeriesRepository(timeseries_collection)


def insert_time_series_point(asset_id, source_id, business_date, metrics_dict, provenance=None, source_metadata=None, asset_metadata=None):
    """
    Saves a single day's market price to MongoDB following the temporal rules.
    The ingest_id protects reruns from creating duplicate records while allowing new versions to append.
    """
    if provenance is None:
        provenance = {"source_name": source_id, "source_url": None, "query_parameters": {}}

    ingest_id = _generate_ingest_id(asset_id, source_id, business_date, metrics_dict, provenance)
    attributes = source_metadata.get("attributes") if source_metadata and source_metadata.get("attributes") else sorted(metrics_dict.keys())
    document = {
        "asset_id": asset_id,
        "data_source_id": source_id,
        "business_date": business_date,
        "system_date": _utc_now(),
        "metrics": metrics_dict,
        "attributes": attributes,
        "provenance": provenance,
        "ingest_id": ingest_id,
    }

    result = timeseries_collection.update_one(
        {"ingest_id": ingest_id},
        {"$setOnInsert": document},
        upsert=True,
    )

    asset_update = {
        "$setOnInsert": {"asset_id": asset_id, "first_seen": document["system_date"]},
        "$set": {"last_seen": document["system_date"], "active": True},
        "$addToSet": {"supported_indicators": {"$each": source_metadata.get("attributes", []) if source_metadata else []}},
    }
    if asset_metadata:
        for field in ["asset_type", "description", "region", "instrument_class"]:
            if asset_metadata.get(field):
                asset_update["$set"][field] = asset_metadata[field]
    if source_metadata and source_metadata.get("vendor_id"):
        asset_update["$set"]["primary_vendor_id"] = source_metadata["vendor_id"]
        asset_update["$set"]["primary_vendor_name"] = source_metadata.get("vendor_name")
        asset_update["$set"]["primary_vendor_description"] = source_metadata.get("vendor_description")

    assets_collection.update_one(
        {"asset_id": asset_id},
        asset_update,
        upsert=True,
    )

    source_update = {
        "$setOnInsert": {
            "data_source_id": source_id,
            "display_name": source_metadata.get("display_name", source_id) if source_metadata else source_id,
            "description": source_metadata.get("description") if source_metadata else None,
            "attributes": source_metadata.get("attributes", []) if source_metadata else [],
            "vendor_id": source_metadata.get("vendor_id") if source_metadata else None,
            "vendor_name": source_metadata.get("vendor_name") if source_metadata else None,
            "vendor_description": source_metadata.get("vendor_description") if source_metadata else None,
            "supported_indicators": source_metadata.get("attributes", []) if source_metadata else [],
            "first_seen": document["system_date"],
        },
        "$set": {"last_seen": document["system_date"], "active": True},
    }
    sources_collection.update_one(
        {"data_source_id": source_id},
        source_update,
        upsert=True,
    )

    if result.upserted_id:
        print(f" Successfully saved document with ID: {result.upserted_id}")
    else:
        print(f" Skipped duplicate ingestion for {asset_id} / {business_date} / {source_id}")

    return result.upserted_id


def mark_asset_deleted(asset_id, effective_date=None, source_id=None, reason=None):
    asset_id = str(asset_id).strip().upper()
    if not asset_id:
        raise ValueError("Asset id is required for soft delete.")

    if effective_date is None:
        effective_date = datetime.utcnow().date().isoformat()

    marker = {
        "asset_id": asset_id,
        "data_source_id": source_id or "SYSTEM.DELETE",
        "business_date": effective_date,
        "system_date": _utc_now(),
        "deleted": True,
        "metrics": {},
        "provenance": {
            "reason": reason or "soft delete marker",
            "source": "warehouse repository",
        },
        "ingest_id": _generate_ingest_id(asset_id, source_id or "SYSTEM.DELETE", effective_date, {}, {"reason": reason or "soft delete marker"}),
    }

    timeseries_collection.update_one(
        {"ingest_id": marker["ingest_id"]},
        {"$setOnInsert": marker},
        upsert=True,
    )

    assets_collection.update_one(
        {"asset_id": asset_id},
        {"$set": {"active": False, "last_seen": marker["system_date"]}},
    )

    print(f"Marked {asset_id} as deleted from {effective_date}.")
    return marker["ingest_id"]


def query_latest_timeseries(asset_id, source_id=None, start_date=None, end_date=None, as_of_system_date=None, limit=100, include_deleted=False):
    """
    Query latest time-series records for an asset/source.

    Supports optional `as_of_system_date` to perform "as-of" historical queries
    by returning only records with `system_date` <= provided timestamp.
    """
    query = {"asset_id": asset_id}
    if source_id:
        query["data_source_id"] = source_id
    if start_date:
        query["business_date"] = {"$gte": start_date}
    if end_date:
        query.setdefault("business_date", {})["$lte"] = end_date
    # Support as-of system date filtering (accepts datetime or ISO string)
    if as_of_system_date:
        if isinstance(as_of_system_date, datetime):
            iso_as_of = as_of_system_date.replace(microsecond=0).isoformat() + "Z"
        else:
            iso_as_of = str(as_of_system_date)
        query["system_date"] = {"$lte": iso_as_of}
    if not include_deleted:
        query["deleted"] = {"$ne": True}

    pipeline = [
        {"$match": query},
        {"$sort": {"business_date": -1, "system_date": -1}},
        {"$group": {"_id": "$business_date", "doc": {"$first": "$$ROOT"}}},
        {"$replaceRoot": {"newRoot": "$doc"}},
        {"$sort": {"business_date": -1}},
        {"$limit": limit},
    ]
    return list(timeseries_collection.aggregate(pipeline))


def query_latest_timeseries_for_assets(asset_ids, start_date=None, end_date=None, include_deleted=False):
    query = {"asset_id": {"$in": asset_ids}}
    if start_date:
        query["business_date"] = {"$gte": start_date}
    if end_date:
        query.setdefault("business_date", {})["$lte"] = end_date
    if not include_deleted:
        query["deleted"] = {"$ne": True}

    pipeline = [
        {"$match": query},
        {"$sort": {"asset_id": 1, "data_source_id": 1, "business_date": 1, "system_date": -1}},
        {"$group": {"_id": {"asset_id": "$asset_id", "data_source_id": "$data_source_id", "business_date": "$business_date"}, "doc": {"$first": "$$ROOT"}}},
        {"$replaceRoot": {"newRoot": "$doc"}},
        {"$sort": {"asset_id": 1, "data_source_id": 1, "business_date": 1}},
    ]
    return list(timeseries_collection.aggregate(pipeline))


def query_asset_lineage(asset_id, source_id=None, limit=200):
    query = {"asset_id": asset_id}
    if source_id:
        query["data_source_id"] = source_id
    return list(timeseries_collection.find(query).sort([("business_date", -1), ("system_date", -1)]).limit(limit))


def query_source_lineage(source_id, limit=200):
    query = {"data_source_id": source_id}
    return list(timeseries_collection.find(query).sort([("business_date", -1), ("system_date", -1)]).limit(limit))


def query_time_series_schema(asset_id=None, source_id=None):
    query = {}
    if asset_id:
        query["asset_id"] = asset_id
    if source_id:
        query["data_source_id"] = source_id

    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": {
                "asset_id": "$asset_id",
                "data_source_id": "$data_source_id",
            },
            "indicator_names": {"$first": "$attributes"},
            "sample_record": {"$first": "$$ROOT"},
        }},
        {"$project": {
            "asset_id": "$_id.asset_id",
            "data_source_id": "$_id.data_source_id",
            "indicator_names": 1,
            "sample_business_date": "$sample_record.business_date",
            "sample_attributes": "$sample_record.attributes",
        }},
        {"$sort": {"asset_id": 1, "data_source_id": 1}},
    ]

    results = list(timeseries_collection.aggregate(pipeline))
    for entry in results:
        source_doc = sources_collection.find_one({"data_source_id": entry["data_source_id"]}, {"_id": 0})
        if source_doc:
            entry["vendor_id"] = source_doc.get("vendor_id")
            entry["vendor_name"] = source_doc.get("vendor_name")
            entry["vendor_description"] = source_doc.get("vendor_description")
            entry["source_attributes"] = source_doc.get("attributes", [])
    return results


def query_asset_instrument_details(asset_id):
    asset = assets_collection.find_one({"asset_id": asset_id}, {"_id": 0})
    if not asset:
        return None

    source_ids = list(timeseries_collection.distinct("data_source_id", {"asset_id": asset_id}))
    data_sources = list(sources_collection.find({"data_source_id": {"$in": source_ids}}, {"_id": 0}).sort("data_source_id", 1))

    return {
        "asset": asset,
        "linked_data_sources": data_sources,
        "indicator_schema": asset.get("supported_indicators", []),
        "primary_vendor_id": asset.get("primary_vendor_id"),
        "primary_vendor_name": asset.get("primary_vendor_name"),
        "primary_vendor_description": asset.get("primary_vendor_description"),
    }


def query_vendor_assets(vendor_id):
    source_ids = list(sources_collection.distinct("data_source_id", {"vendor_id": vendor_id}))
    asset_ids = list(timeseries_collection.distinct("asset_id", {"data_source_id": {"$in": source_ids}}))
    assets = list(assets_collection.find({"asset_id": {"$in": asset_ids}}, {"_id": 0}).sort("asset_id", 1))
    return assets


def _parse_iso_to_datetime(value):
    """Parse an ISO string (optionally ending with 'Z') or normalize a datetime to naive UTC."""
    if isinstance(value, datetime):
        dt = value.replace(microsecond=0)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    if isinstance(value, str):
        s = value.strip()
        if s.endswith("Z"):
            s = s[:-1]
        try:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt.replace(microsecond=0)
        except Exception:
            return None
    return None


def migrate_system_date_to_datetime(batch_size: int = 500, dry_run: bool = True):
    """Migrate `system_date` string values to MongoDB datetime objects.

    If `dry_run` is True the function will only report how many documents would be
    migrated. When False it will perform updates in batches and return the count migrated.
    """
    filter_q = {"system_date": {"$type": "string"}}
    total = timeseries_collection.count_documents(filter_q)
    print(f"Found {total} documents with string-valued system_date.")
    if dry_run:
        return total

    migrated = 0
    cursor = timeseries_collection.find(filter_q, {"_id": 1, "system_date": 1})
    for doc in cursor.batch_size(batch_size):
        old_val = doc.get("system_date")
        dt = _parse_iso_to_datetime(old_val)
        if dt is None:
            print(f"Skipping _id={doc.get('_id')}: cannot parse system_date {old_val}")
            continue
        res = timeseries_collection.update_one({"_id": doc["_id"]}, {"$set": {"system_date": dt}})
        if res.modified_count > 0:
            migrated += 1

    print(f"Migrated {migrated} documents to datetime system_date.")
    return migrated
