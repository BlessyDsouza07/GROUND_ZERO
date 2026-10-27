from __future__ import annotations

import logging

from fastapi import FastAPI

from layer2.api.routes import router as hive_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Ground Zero — Layer 2: HIVE Recommendation Engine",
    description="Hard Filters -> Personal Fit Score -> Weather scheduling -> Slot assembly -> Transport tagging.",
    version="0.1.0",
)
app.include_router(hive_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "layer": "layer2"}
