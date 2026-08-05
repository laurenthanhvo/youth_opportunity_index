# YOI AI Assistant starter

This is a local MVP using:

- Gemini 3.5 Flash-Lite
- FastAPI
- DuckDB
- Six approved, read-only tools
- Basic token, latency, tool-selection, and cost logging
- A small evaluation set

## 1. Put this folder in the repository

Rename this folder to:

```text
assistant_backend
```

Your repository should look like:

```text
youth_opportunity_index/
├── assistant_backend/
├── data/
├── datasets.html
├── index.html
└── map.html
```

## 2. Create a clean environment

From the repository root:

```bash
python3 -m venv .venv-ai
source .venv-ai/bin/activate
python -m pip install --upgrade pip
python -m pip install -r assistant_backend/requirements.txt
```

## 3. Add the Gemini key

Create a Gemini API key in Google AI Studio.

Then:

```bash
cp assistant_backend/.env.example assistant_backend/.env
```

Open `assistant_backend/.env` and paste the key:

```text
GEMINI_API_KEY=your_key_here
```

Never commit `.env`.

## 4. Start the backend

From the repository root:

```bash
uvicorn assistant_backend.app.main:app \
  --reload \
  --port 8000
```

Check:

```text
http://127.0.0.1:8000/health
```

The health response should report that the tract CSV, region CSV,
metadata CSV, and methodology file exist.

## 5. Test one question

```bash
curl -X POST \
  http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Which five tracts have the lowest Youth Supports scores?"}'
```

The response includes:

- `answer`
- `tool_trace`
- `usage`
- `response_time_ms`
- `estimated_paid_cost_usd`
- `estimated_current_cost_usd` (uses `BILLING_MODE` from `.env`)

## 6. Connect the existing frontend

Copy the logic from `frontend-example.js` into the dashboard chat code
and point it to:

```text
http://127.0.0.1:8000/api/chat
```

The API expects:

```json
{
  "message": "How do East San Diego and Metro San Diego compare?"
}
```

## 7. Run the first evaluation

From the repository root:

```bash
python assistant_backend/eval/run_eval.py
```

Review:

```text
assistant_backend/eval/results.csv
```

Manually fill in the accuracy, citation, caveat, and review columns.
Do not add hybrid routing until the results show a repeatable category
where Flash-Lite fails.

## Current MVP scope

Supported:

- County-region summaries
- Census-tract summaries by GEOID
- Comparing two exact geographies
- Lowest-scoring tract rankings
- Indicator metadata lookup
- Methodology retrieval
- Relative map links

Not yet supported:

- Fuzzy neighborhood-to-tract resolution
- ZIP, supervisor-district, or council-district queries
- Web search
- User-uploaded file analysis
- Autonomous multi-step reports
- Fine-tuning
- Automatic fallback to a stronger model

## Security notes

- All SQL identifiers are selected from approved internal lists.
- User values are passed as query parameters.
- The model cannot run arbitrary SQL or Python.
- The API limits each turn to two approved tool calls.
- The backend is read-only and does not modify YOI data.
