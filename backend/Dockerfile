# Runtime image for Railway (API service; the WhatsApp worker reuses it with a different
# start command). Build context: backend/
#
# Pinned to a patch release, not the floating `3.13-slim` tag: a cached base layer can otherwise
# keep serving an old interpreter. Bump it when Python ships a security release (3.13.18 carries
# CVE-2026-115557 for the compromised eMudhra CA keys); `make audit` reports the next one.
FROM python:3.13.18-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app

RUN useradd --create-home --uid 10001 appuser
USER appuser

ENV PATH="/app/.venv/bin:$PATH" \
    APP_ENV=production \
    PORT=8000
EXPOSE 8000

# API process. Worker service overrides with: python -m app.worker.main
CMD ["python", "-m", "app.serve"]
