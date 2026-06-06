#!/usr/bin/env python3
import os
import sys
import json
from pathlib import Path

# Ensure repository root is on sys.path so `app` package is importable when running
# this script from the scripts/ folder.
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

from app import create_app

app = create_app()
client = app.test_client()


def print_resp(resp, limit=None):
    print(resp.status_code)
    data = resp.get_data(as_text=True)
    if limit and len(data) > limit:
        print(data[:limit] + "\n... (truncated)")
    else:
        print(data)


print("--- GET /api/assets/ids ---")
resp = client.get("/api/assets/ids")
print_resp(resp, limit=2000)

print("\n--- GET /api/time-series?assetId=BTCUSD&dataSourceId=NASDAQ-DATA-LINK.QDL/BITFINEX ---")
resp = client.get("/api/time-series?assetId=BTCUSD&dataSourceId=NASDAQ-DATA-LINK.QDL/BITFINEX")
print_resp(resp, limit=2000)

print("\n--- GET /api/analytics/trends ---")
resp = client.get("/api/analytics/trends")
print_resp(resp, limit=2000)
