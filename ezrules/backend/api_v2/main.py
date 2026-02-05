"""
FastAPI application for ezrules API v2.

This is the main entry point for the new FastAPI-based API.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ezrules.backend.api_v2.routes import auth, labels, outcomes, rules

# Create FastAPI app
app = FastAPI(
    title="ezrules API",
    description="Transaction monitoring engine API",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS
# In development, allow Angular dev server (localhost:4200)
# In production, this should be configured via environment variables
cors_origins = [
    "http://localhost:4200",  # Angular dev server
    "http://127.0.0.1:4200",
    "http://localhost:8888",  # Legacy Flask manager
    "http://127.0.0.1:8888",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/ping")
async def ping():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "ezrules API",
        "version": "2.0.0",
        "docs": "/docs",
    }


# =============================================================================
# REGISTER ROUTERS
# =============================================================================

# Auth routes: /api/v2/auth/login, /api/v2/auth/refresh, /api/v2/auth/me
app.include_router(auth.router)

# Rules routes: /api/v2/rules/*
app.include_router(rules.router)

# Outcomes routes: /api/v2/outcomes/*
app.include_router(outcomes.router)

# Labels routes: /api/v2/labels/*
app.include_router(labels.router)
