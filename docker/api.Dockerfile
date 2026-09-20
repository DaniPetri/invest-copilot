FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1 \
    MODEL_CACHE_DIR=/models
COPY backend/pyproject.toml backend/uv.lock backend/.python-version backend/
RUN cd backend && uv sync --frozen --no-dev --no-install-project
COPY backend backend
COPY evals evals
COPY fixtures fixtures
COPY contracts contracts
COPY scripts scripts
COPY frontend/fixtures frontend/fixtures
COPY docker/api-entrypoint.sh /usr/local/bin/api-entrypoint
RUN chmod +x /usr/local/bin/api-entrypoint
EXPOSE 8000
ENTRYPOINT ["api-entrypoint"]
