# Evaluator API

The evaluator endpoint is part of the unified FastAPI service.

## Base URL

`http://localhost:8888`

## Run Locally

--8<-- "snippets/start-api.md"

## Endpoint

### Evaluate Event

`POST /api/v2/evaluate`

Evaluates an event against the current rule configuration and stores evaluation results.

Request and response schemas are defined in OpenAPI and available in the interactive docs.

## Authentication

`/api/v2/evaluate` is currently intended for internal/service use and does not require user authentication.

## Live API Documentation (Recommended)

--8<-- "snippets/openapi-links.md"

Use these as the source of truth for request/response models and status codes.
