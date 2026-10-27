from __future__ import annotations

import logging

from fastapi import FastAPI

from layer1.api.routes import router as survey_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Ground Zero — Layer 1: Soul Survey",
    description="9-question survey producing a TouristProfile.",
    version="0.1.0",
)
app.include_router(survey_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "layer": "layer1"}
