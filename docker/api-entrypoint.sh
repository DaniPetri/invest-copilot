#!/bin/sh
# First start: build the synthetic universe and the search index (a few seconds, plus a one-off ~220 MB model
# download that lands in the /models volume). Later starts skip this.
set -e
cd /app/backend
if [ ! -f /app/data/generated/products.json ]; then
  echo "[api] first start: make data"
  uv run --no-dev python -m app.data.generate
fi
if [ ! -f /app/data/generated/bm25.pkl ]; then
  echo "[api] first start: make ingest"
  uv run --no-dev python -m app.rag.index
fi
exec uv run --no-dev uvicorn app.main:app --host 0.0.0.0 --port 8000
