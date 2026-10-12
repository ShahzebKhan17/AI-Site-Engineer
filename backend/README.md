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

Open `http://localhost:8000/docs` to inspect the API. Available endpoints include `GET /health` and `POST /calculations/column-longitudinal-bar`.

Every calculation request must include source references. The API only totals explicit reviewed inputs; future rules modules will resolve code provisions and validate their applicability before calling the calculator.
