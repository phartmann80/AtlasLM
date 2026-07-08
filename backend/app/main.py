import logging
# Suppress httpx request logger to prevent provider URL leaks in logs (T11)
logging.getLogger("httpx").setLevel(logging.WARNING)

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .core.config import settings
from .core.database import engine, Base
from .api.endpoints import router as api_router
from .middleware.auth_middleware import AuthMiddleware
from .stripe_webhook import router as stripe_router

logger = logging.getLogger(__name__)

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
except Exception as e:
    logger.exception(f"FATAL: Could not connect to database / enable pgvector / create tables: {e}")
    raise

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3100",
        "http://localhost:3010",
        "https://atlaslm.cloud",
        "https://www.atlaslm.cloud",
        "https://atlaslm.vercel.app",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(AuthMiddleware)

app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(stripe_router)

from .routes import sources
app.include_router(sources.router)


@app.get("/", tags=["system"])
def read_root():
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "docs_url": "/docs",
    }


@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
