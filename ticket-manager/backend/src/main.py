from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from src.api.v1.router import router
from src.core.config import settings
from src.core.database import engine
from src.core.logging import RequestLoggingMiddleware, configure_logging

configure_logging()

app = FastAPI(
    title="Ticket Management System",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS: allow only the configured frontend origin — never use wildcard in production
# (F-ADD-02 security requirement). Set FRONTEND_URL in .env for each environment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)
app.include_router(router)


@app.get("/health", tags=["System"])
async def health() -> dict:
    return {"status": "ok"}


@app.get("/ready", tags=["System"])
async def ready() -> dict:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unreachable"
        )
