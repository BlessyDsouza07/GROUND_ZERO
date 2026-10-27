from __future__ import annotations

import logging

from fastapi import FastAPI

from layer0.api.admin import router as admin_router
from layer0.api.routes import router as places_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Ground Zero — Layer 0: Background Engine",
    description="Master Data Core ingestion, bias audit, freshness, and community submissions.",
    version="0.1.0",
)
app.include_router(places_router)
app.include_router(admin_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "layer": "layer0"}
