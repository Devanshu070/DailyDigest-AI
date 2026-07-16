"""
app/api/app.py — FastAPI application instance.

Wires together:
  - CORS middleware (public access, open to all origins)
  - Lifespan handler for startup/shutdown logging
  - Route routers (added in Phase 2)
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

log = logging.getLogger(__name__)

APP_VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("DailyDigest API v%s starting up…", APP_VERSION)
    yield
    log.info("DailyDigest API shutting down.")


app = FastAPI(
    title="DailyDigest AI",
    description="REST API for DailyDigest-AI — browse sources, articles, digests, and trigger pipeline runs.",
    version=APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ───────────────────────────────────────────────────────────────────────
# Public access — no auth yet. Tighten this when adding a frontend origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Root Endpoint ──────────────────────────────────────────────────────────────
@app.get("/", tags=["system"])
async def root():
    return {
        "service": "DailyDigest-AI",
        "status": "healthy",
        "version": APP_VERSION,
        "docs": "/docs",
        "health": "/api/v1/health"
    }

# ── Routers ────────────────────────────────────────────────────────────────────
from app.api.routes import health, sources, articles, pipeline, users

app.include_router(health.router,    prefix="/api/v1")
app.include_router(users.router,     prefix="/api/v1")
app.include_router(sources.router,   prefix="/api/v1")
app.include_router(articles.router,  prefix="/api/v1")
app.include_router(pipeline.router,  prefix="/api/v1")
