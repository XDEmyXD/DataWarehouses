# Acme Ltd Financial Data Warehouse

## Overview
This is a student project that shows a simple financial data platform for Acme Ltd.

It includes:
- ingestion from Nasdaq Data Link with fallback sample data
- MongoDB storage for time-series data
- a Flask API for assets, sources, and time-series queries
- analytics code that creates summaries and simple regression predictions
- a small MCP tool layer for model-driven query simulation

## Requirements

- Python 3.11
- MongoDB (local or Docker)
- Docker and Docker Compose (optional but recommended)

## Setup

1. Copy or update `.env` with your MongoDB URI and Nasdaq API key:

```env
MONGO_URI=mongodb://localhost:27017/
NASDAQ_API_KEY=your_api_key_here
```

2. Install dependencies locally:

```bash
python -m pip install -r requirements
```

3. Start MongoDB locally or with Docker before running the app.

4. If you want analytics to run, make sure `pyspark` installs successfully. The app can still start without PySpark, but analytics functions will be skipped.

## Docker Compose

Use Docker Compose to run MongoDB and the Flask app together:

```bash
docker compose up --build
```

The app will be available at `http://localhost:8080`.

Open `http://localhost:8080` in your browser to access the new Acme dashboard.

## Running the project

1. Start MongoDB locally or via Docker.
2. Install Python dependencies:

```bash
python -m pip install -r requirements
```

3. Start the Flask app:

```bash
python app.py
```

4. Open the dashboard at `http://localhost:8080`.

If you want to run specific parts manually:

- Ingestion only:

```bash
python ingest.py
```

- Run every supported asset ingestion and analytics with the default batch pipeline:

```bash
curl -X POST http://localhost:8080/run-pipeline
```

- Analytics only:

```bash
python analytics.py
```

- MCP tool simulator:

```bash
python mcp_server.py
```

## No-code UI guide

The dashboard includes simple controls for non-developers:

- **Presets**: pick a built-in preset to populate common asset lists (e.g. Top Crypto, Top Tech).
- **Quick ranges**: set common date ranges (7 / 30 / 90 days) with one click.
- **Assets input**: type asset symbols separated by commas (e.g. `BTCUSD,ETHUSD,AAPL`).
- **Run buttons**: `Run ingestion only` or `Run full pipeline` will act on the selected assets.
- **Assistant (Quick Chat)**: ask for a human-friendly summary of recent analytics for an asset.
- **Export / Copy**: copy the output to clipboard, download JSON, or export records as CSV.

These controls are intended to let a non-technical user run common workflows without writing code.

## Running tests

Unit tests were added for `CommonService` and `ChatService` under the `tests/` folder.

Install test dependencies and run the suite with:

```bash
python -m pip install -r requirements
pytest -q
```

The tests use `unittest.mock` to avoid needing a live database or Spark installation.

## API Endpoints

- `GET /api/assets?limit=20&offset=0`
- `GET /api/assets/<asset_id>`
- `POST /api/assets/<asset_id>/delete`
- `GET /api/data-sources?limit=20&offset=0`
- `GET /api/data-sources/<data_source_id>`
- `GET /api/data?assetId=BTCUSD&dataSourceId=NASDAQ-DATA-LINK.QDL/BITFINEX&startBusinessDate=2026-06-01&endBusinessDate=2026-06-06&includeAttributes=true`
- `GET /api/data?assetId=BTCUSD&dataSourceId=NASDAQ-DATA-LINK.QDL/BITFINEX&asOfSystemDate=2026-06-06`

## MCP Tools

The MCP layer now includes:
- `list_assets`
- `get_asset_details`
- `list_data_sources`
- `get_data_source_details`
- `get_time_series_data`
- `get_analytics_summary`
- `get_market_predictions`
- `get_asset_analytics`

Each tool returns structured JSON and is intended for data lookup only, not financial advice.

## Local LLM (llama.cpp) Support

The project supports running a local LLM using `llama.cpp` via the `llama-cpp-python` package.
This allows you to run the assistant fully offline without using paid APIs.

Quick setup:

1. Install the Python package (optional; only needed for local LLM use):

```bash
python -m pip install llama-cpp-python
```

2. Download a compatible GGUF or ggml model (e.g., a Llama 2 small/medium variant) and note its filesystem path.

3. Set environment variables:

```bash
# Path to your local model file
export LLAMA_MODEL_PATH=/path/to/your/model.gguf
# Enable local backend
export LOCAL_LLM=llama_cpp
```

On Windows PowerShell:

```powershell
setx LLAMA_MODEL_PATH "C:\path\to\model.gguf"
setx LOCAL_LLM "llama_cpp"
```

4. Start the Flask app as usual. The assistant will use the local LLM and can call MCP tools via the JSON tool-calling protocol described in the code.

Notes:
- Local models vary in quality. Choose an appropriate model size for your hardware.
- If you don't configure `LOCAL_LLM`, the system will default to the configured remote LLM (Mistral) when available.

## Notes

- `analytics.py` uses PySpark for the summary and prediction steps.
- `app.py` has pagination and a UI endpoint for the dashboard.
- `mcp_server.py` gives a simple tool interface for the assistant.
- `ingest.py` normalizes metrics into more detailed fields.

## Optional deliverables

- `IIAGen Usage Statement.pdf`: create a document describing the generative AI prompts and tool boundaries used.
- Demo video: record the pipeline from ingestion through API and MCP tool interaction.
