# uv as a named stage: Dependabot only tracks images on FROM lines.
FROM ghcr.io/astral-sh/uv:0.13.10 AS uv

# ── builder ────────────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

COPY --from=uv /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies first.
# This layer is only rebuilt when pyproject.toml or uv.lock changes,
# keeping iterative app-code rebuilds fast.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy source and install the project itself into the same venv
COPY . .
RUN uv sync --frozen --no-dev

# Bake static files into the image so the runtime stage needs no write access
# collectstatic only imports settings; this throwaway key is not kept in the image env.
RUN DJANGO_SECRET_KEY=collectstatic-build-only .venv/bin/python manage.py collectstatic --noinput

# ── runtime ────────────────────────────────────────────────────────────────
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/app/.venv/bin:$PATH"

RUN addgroup --system app \
 && adduser --system --ingroup app app \
 && install -d -m 755 -o app -g app /app

WORKDIR /app

COPY --from=builder --chown=app:app /app /app
COPY --chmod=755 entrypoint.sh /entrypoint.sh

USER app

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "otter_finance_manager.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
