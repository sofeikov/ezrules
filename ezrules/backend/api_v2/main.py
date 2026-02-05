"""
FastAPI application for ezrules API v2.

This is the main entry point for the new FastAPI-based API.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ezrules.backend.api_v2.routes import (
    analytics,
    audit,
    auth,
    labels,
    outcomes,
    roles,
    rules,
    user_lists,
    users,
)

# Create FastAPI app
app = FastAPI(
    title="ezrules API",
    description="Transaction monitoring engine API",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS
# In development, allow all localhost origins (any port)
# In production, this should be configured via environment variables
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
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

# Analytics routes: /api/v2/analytics/*
app.include_router(analytics.router)

# Users routes: /api/v2/users/*
app.include_router(users.router)

# Roles routes: /api/v2/roles/*
app.include_router(roles.router)

# User Lists routes: /api/v2/user-lists/*
app.include_router(user_lists.router)

# Audit Trail routes: /api/v2/audit/*
app.include_router(audit.router)
