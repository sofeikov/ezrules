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
    backtesting,
    evaluator,
    field_types,
    labels,
    outcomes,
    roles,
    rules,
    user_lists,
    users,
)
from ezrules.core.application_context import set_organization_id, set_user_list_manager
from ezrules.core.user_lists import PersistentUserListManager
from ezrules.models.database import db_session
from ezrules.settings import app_settings

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


# =============================================================================
# INITIALIZE APPLICATION CONTEXT
# =============================================================================
# Set up the user list manager so rule parsing can resolve @ListName references.
# Without this, the AtNotationConverter falls back to the StaticUserListManager
# which only knows about a few hardcoded lists.
_user_list_manager = PersistentUserListManager(db_session=db_session, o_id=app_settings.ORG_ID)
set_organization_id(app_settings.ORG_ID)
set_user_list_manager(_user_list_manager)


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

# Evaluator routes: /api/v2/evaluate, /api/v2/ping (merged from evaluator service)
app.include_router(evaluator.router)

# Backtesting routes: /api/v2/backtesting/*
app.include_router(backtesting.router)

# Field Types routes: /api/v2/field-types/*
app.include_router(field_types.router)
