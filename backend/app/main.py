from fastapi import FastAPI

from app.routers.calculations import router as calculations_router
from app.routers.drawings import router as drawings_router
from app.routers.health import router as health_router
from app.routers.questions import router as questions_router

app = FastAPI(
    title="SiteFlow Calculation API",
    version="0.1.0",
    description="Deterministic calculation service for reviewed structural drawing inputs.",
)
app.include_router(health_router)
app.include_router(calculations_router)
app.include_router(drawings_router)
app.include_router(questions_router)
