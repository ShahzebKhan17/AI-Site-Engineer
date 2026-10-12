# Calculation API

This FastAPI service owns deterministic engineering calculations. RAG supplies cited and validated inputs; it must never produce the calculation result itself.

## Run locally

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000/docs` to inspect the API. Available endpoints include `GET /health`, `POST /drawings/extract`, and `POST /calculations/column-longitudinal-bar`.

`POST /drawings/extract` accepts a digitally generated PDF up to 25 MB and returns text chunks with page citations. It is deliberately a synchronous development endpoint; production ingestion will persist the upload and enqueue its processing.

Every calculation request must include source references. The API only totals explicit reviewed inputs; future rules modules will resolve code provisions and validate their applicability before calling the calculator.
