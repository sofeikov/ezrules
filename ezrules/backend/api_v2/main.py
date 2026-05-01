"""
FastAPI application for ezrules API v2.

This is the main entry point for the new FastAPI-based API.
"""

from collections.abc import Sequence

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse

from ezrules.backend.api_v2.auth.dependencies import (
    SessionLocal,
    bind_request_org_context,
    get_org_id_for_access_token,
    get_org_id_for_api_key,
)
from ezrules.backend.api_v2.routes import (
    alerts,
    analytics,
    api_keys,
    audit,
    auth,
    backtesting,
    evaluator,
    field_types,
    labels,
    outcomes,
    roles,
    rollouts,
    rules,
    settings,
    shadow,
    tested_events,
    user_lists,
    users,
)
from ezrules.core.application_context import reset_context
from ezrules.models.database import db_session
from ezrules.settings import Settings, app_settings


def build_cors_middleware_kwargs(settings: Settings) -> dict[str, bool | str | Sequence[str] | None]:
    allowed_origins = settings.cors_allowed_origins

    return {
        "allow_origins": allowed_origins,
        "allow_origin_regex": settings.CORS_ALLOW_ORIGIN_REGEX,
        "allow_credentials": True,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }


# Create FastAPI app
app = FastAPI(
    title="ezrules API",
    description="Transaction monitoring engine API",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Default behavior is same-origin only. Local development and split-origin
# deployments must opt in to browser origins explicitly.
app.add_middleware(CORSMiddleware, **build_cors_middleware_kwargs(app_settings))


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > app_settings.MAX_BODY_SIZE_KB * 1024:
            return JSONResponse(status_code=413, content={"detail": "Request body too large"})
        return await call_next(request)


app.add_middleware(BodySizeLimitMiddleware)


def _prime_request_context_from_headers(request: StarletteRequest, db) -> None:
    """Best-effort context binding before sync dependency/route execution starts."""
    api_key = request.headers.get("X-API-Key")
    if api_key:
        org_id = get_org_id_for_api_key(api_key, db)
        if org_id is not None:
            bind_request_org_context(db, org_id)
            return

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
        org_id = get_org_id_for_access_token(token, db)
        if org_id is not None:
            bind_request_org_context(db, org_id)


@app.middleware("http")
async def cleanup_scoped_db_session(request: StarletteRequest, call_next):
    """Release request-local context and any checked-out scoped DB session."""
    context_db = db_session if app_settings.TESTING else SessionLocal()
    try:
        if request.url.path != "/api/v2/evaluate":
            _prime_request_context_from_headers(request, context_db)
        return await call_next(request)
    finally:
        reset_context()
        if not app_settings.TESTING:
            context_db.close()
            db_session.remove()


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

# Alert and notification routes: /api/v2/alerts/*, /api/v2/notifications/*
app.include_router(alerts.router)

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

# Tested event routes: /api/v2/tested-events/*
app.include_router(tested_events.router)

# Backtesting routes: /api/v2/backtesting/*
app.include_router(backtesting.router)

# Field Types routes: /api/v2/field-types/*
app.include_router(field_types.router)

# Shadow routes: /api/v2/shadow/*
app.include_router(shadow.router)

# Rollout routes: /api/v2/rollouts/*
app.include_router(rollouts.router)

# API Key routes: /api/v2/api-keys/*
app.include_router(api_keys.router)

# Runtime settings routes: /api/v2/settings/*
app.include_router(settings.router)
