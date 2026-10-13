from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.calculations import router as calculations_router
from app.routers.drawings import router as drawings_router
from app.routers.health import router as health_router
from app.routers.questions import router as questions_router

app = FastAPI(
    title="SiteFlow Calculation API",
    version="0.2.0",
    description="Deterministic calculation service for reviewed structural drawing inputs per IS 456 & SP 34.",
)

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(calculations_router)
app.include_router(drawings_router)
app.include_router(questions_router)
