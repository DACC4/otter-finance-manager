# ── builder ───────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Bring in uv (pin the tag for reproducible builds, e.g. uv:0.5.x)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

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
RUN .venv/bin/python manage.py collectstatic --noinput

# ── runtime ───────────────────────────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/app/.venv/bin:$PATH"

# Non-root user
RUN addgroup --system app && adduser --system --ingroup app app

WORKDIR /app

# Copy the virtualenv and application source from the builder.
# --chown sets ownership of the copied files but not the /app directory
# itself (created by WORKDIR as root), so fix that explicitly.
COPY --from=builder --chown=app:app /app /app
RUN chown app:app /app

# entrypoint must be executable; do this as root before switching user
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER app

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "otter_finance_manager.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
