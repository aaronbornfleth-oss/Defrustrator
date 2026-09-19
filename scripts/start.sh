#!/bin/sh
# Render and similar hosts inject PORT. Default matches local Docker / compose.
set -eu
cd /app/backend
exec python -m uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
