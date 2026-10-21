"""
FastAPI app entry point.

Usage:
    uvicorn api.main:app --reload --port 8000
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import agent_actions, auth, categories, tickets

app = FastAPI(title="Agentic CRM API")

# ALLOWED_ORIGINS is a comma-separated list (e.g. the deployed frontend's
# URL); unset keeps the "*" default for local dev against the Vite dev
# server. Auth is a Bearer token, not a cookie, so allow_credentials stays
# False -- browsers reject credentialed requests from a wildcard origin
# anyway, so True here would silently do nothing for "*" and isn't needed
# for an explicit origin list either.
_origins = os.environ.get("ALLOWED_ORIGINS")
allow_origins = [o.strip() for o in _origins.split(",")] if _origins else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(tickets.router)
app.include_router(agent_actions.router)
app.include_router(categories.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
