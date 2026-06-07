# Acme Financial Analytics

What is this?
-------------
A demonstration data pipeline and API designed for educational purposes. The application collects market data, persists it in MongoDB, executes analytical workflows, and provides a REST API wrapper.

System Architecture
-------------------
The core application logic is split into two components:
- run-pipeline: Ingests market data, persists records, and runs statistical analytics (descriptive summaries and regression-based predictions).
- ask-a-question: Interfaces with an external Large Language Model (LLM) to return concise answers to natural language prompts.

Prerequisites
-------------
- Python 3.10+
- MongoDB (Local instance or Docker container)
- Virtual environment tool (venv)

Setup Guide
-----------
1. Navigate to the project root directory.

2. Create and activate a Python virtual environment:
   
   - macOS / Linux:
     python -m venv venv
     source venv/bin/activate

   - Windows (PowerShell):
     python -m venv venv
     .\venv\Scripts\Activate.ps1

3. Install required Python dependencies:
   python -m pip install -r requirements

4. Configure the environment variables. Create a .env file in the root directory:
   
   MONGO_URI=mongodb://localhost:27017/
   # Optional configurations for LLM integration:
   MISTRAL_API_KEY=your_key_here
   MISTRAL_API_URL=https://api.mistral.ai/v1
   MISTRAL_MODEL=your_model_name

5. Dependency Option (PySpark):
   Executing PySpark analytics requires a local Java installation with JAVA_HOME correctly configured. If the Java runtime is not detected, the system automatically falls back to pandas and scikit-learn execution paths.

Deployment
----------
1. Ensure the MongoDB daemon is active.
2. Initialize the Flask application server:
   python run.py

3. Access the API documentation endpoints via a web browser:
   - Swagger UI: http://localhost:8080/api/docs
   - OpenAPI JSON Specification: http://localhost:8080/api/openapi.json

API Usage Examples
------------------
Execute the following curl commands via a secondary terminal window to test endpoint responses.

- Trigger Ingestion and Analytics Pipeline (Bypasses LLM):
  curl -s -X POST -H "Content-Type: application/json" -d '{"assets":["BTCUSD"], "showResults": true}' http://localhost:8080/run-pipeline

- Query LLM Agent Endpoint:
  curl -s -X POST -H "Content-Type: application/json" -d '{"message":"Summarize BTCUSD in one sentence."}' http://localhost:8080/ask-a-question

Pipeline Payload Configuration
------------------------------
The /run-pipeline POST body accepts the following JSON fields:
- assets (array): List of target asset tickers (e.g., ["BTCUSD", "AAPL"]). Defaults to an internal preset array if omitted or left empty.
- omitFields (array): List of metric object keys to filter out before database write (e.g., ["volume"]).
- showResults (boolean): When true, includes the newly generated data summaries and records directly inside the API response body.
- descriptive (boolean): Toggles the descriptive statistical summary generation.
- predictive (boolean): Toggles the predictive ML analysis generation.
- async (boolean): When true, processes the request asynchronously as a background task and returns an immediate response code.

Technical Implementation Notes
------------------------------
- Database Persistence: Appends and queries data inside the "acme_dw" MongoDB database. Key collections include: time_series_data, assets, data_sources, totals, and regression_results.
- Runtime Failbacks: If the PySpark subsystem fails to initialize due to a missing Java environment, the execution context shifts seamlessly to a local pandas and sklearn pipeline.
- Functional Separation: The /run-pipeline endpoint isolates processing to data ingestion and calculations. Natural language processing queries must be routed through /ask-a-question.

Verification Tasks
------------------
1. Modify the array arguments in the "assets" parameter of the /run-pipeline payload to confirm data is dynamically processed.
2. Inject arrays into "omitFields" (e.g., "volume") and query the target MongoDB collection to verify field suppression.
3. Submit multiple discrete questions to /ask-a-question to observe stateless model output consistency.

Testing
-------
To run the automated suite, install the testing requirements and execute:
pytest -q

Note: Ensure a live MongoDB instance is available during execution, or refactor the target blocks to use local mock utilities.

Codebase Directory Structure Map
--------------------------------
- app/ : Contains the initialization logic for the Flask server and endpoint routes.
- data/ingest.py : Manages pipeline ingestion loops and backfill utilities.
- analytics/analytics.py : Core calculation files handling descriptive statistics and predictive logic models.
- db/database.py : Manages connection pooling, client lifecycles, and repository access layers.
- app/mistral_adapter.py & app/llm_agent.py : Houses the connector layers for LLM API integration.

Troubleshooting Procedures
--------------------------
- Review terminal stdout/stderr for explicit alerts (e.g., Java missing runtime notifications, unconfigured LLM keys).
- Confirm the .env file is localized in the root directory and contains a valid MONGO_URI string.
- To use the PySpark pipeline, install an appropriate Java Development Kit (JDK), bind the system binary path to JAVA_HOME, and reinstall the pyspark library.