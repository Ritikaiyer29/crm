"""
FastAPI app entry point.

Usage:
    uvicorn api.main:app --reload --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import agent_actions, auth, categories, tickets

app = FastAPI(title="Agentic CRM API")

# Wide open for local dev against the Vite dev server; tighten to the real
# deployed frontend origin once that exists (Phase 8 deploy step).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
