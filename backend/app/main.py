from fastapi import FastAPI

from app.routers.health import router as health_router

app = FastAPI(
    title="SiteFlow Calculation API",
    version="0.1.0",
    description="Deterministic calculation service for reviewed structural drawing inputs.",
)
app.include_router(health_router)
