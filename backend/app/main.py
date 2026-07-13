import logging
import os
# Suppress httpx request logger to prevent provider URL leaks in logs (T11)
logging.getLogger("httpx").setLevel(logging.WARNING)

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .core.config import settings
from .core.database import engine, Base
from .api.endpoints import router as api_router
from .api.internal_ai import router as internal_ai_router
from .middleware.auth_middleware import AuthMiddleware
from .stripe_webhook import router as stripe_router

logger = logging.getLogger(__name__)

database_ready = False
database_error: str | None = None

try:
    # Enable pgvector BEFORE SQLAlchemy creates VECTOR columns.
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()

        res = conn.execute(
            text("SELECT extname FROM pg_extension WHERE extname='vector'")
        ).fetchone()
        if not res:
            raise RuntimeError("pgvector extension 'vector' not present after CREATE EXTENSION")

    # Import models to register them with metadata.
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized successfully (pgvector vector enabled).")
    database_ready = True
except Exception as e:
    database_error = str(e)
    logger.exception(f"Could not connect to database / enable pgvector / create tables: {e}")
    if not os.getenv("VERCEL"):
        raise

production_env = settings.ATLAS_ENV.lower() in {"prod", "production"}

app = FastAPI(
    title=settings.PROJECT_NAME,
    docs_url=None if production_env else "/docs",
    redoc_url=None if production_env else "/redoc",
    openapi_url=None if production_env else "/openapi.json",
)

configured_origins = {
    origin.strip().rstrip("/")
    for origin in settings.ATLAS_ALLOWED_ORIGINS.split(",")
    if origin.strip()
}
configured_origins.update({
    "http://localhost:3000",
    "http://localhost:3100",
    "http://localhost:3010",
    "https://atlaslm.vercel.app",
    "https://atlaslm.cloud",
    "https://www.atlaslm.cloud",
})

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(configured_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(AuthMiddleware)

app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(internal_ai_router)
app.include_router(stripe_router)

from .routes import sources
app.include_router(sources.router)


@app.get("/", tags=["system"])
def read_root():
    response = {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
    }
    if not production_env:
        response["docs_url"] = "/docs"
    return response


@app.get("/health", tags=["system"])
async def health_check():
    if database_ready:
        return {"status": "healthy", "database": "ready"}
    return {
        "status": "degraded",
        "database": "unavailable",
        "detail": "DATABASE_URL must point to a managed Postgres database with pgvector enabled.",
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
