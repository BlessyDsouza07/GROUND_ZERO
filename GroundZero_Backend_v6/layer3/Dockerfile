# Ground Zero — Layer 3 standalone image.
# Build:  docker build -t ground-zero-layer3 .
# Run:    docker run --rm -p 8004:8004 --env-file .env -v $(pwd)/../layer0_fixed/data_output:/layer0_data:ro ground-zero-layer3
#
# This container only needs read access to Layer 0's data_output folder (master_data_core.json,
# ground_zero.db, live_tide_cache.json, live_events_cache.json). It never writes there.

FROM python:3.12-slim

WORKDIR /app

# tzdata for Asia/Kolkata; curl for the HEALTHCHECK
RUN apt-get update && apt-get install -y --no-install-recommends tzdata curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/data_output

ENV LAYER3_HOST=0.0.0.0 \
    LAYER3_PORT=8004 \
    LAYER0_DATA_DIR=/layer0_data \
    PYTHONUNBUFFERED=1

EXPOSE 8004

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:${LAYER3_PORT}/health || exit 1

CMD ["python", "run_layer3.py", "--serve"]
