#!/bin/bash
cd /home/claude/backend/integrated_v2
set -a
source .env
set +a
exec uvicorn main:app --host 127.0.0.1 --port 8000
