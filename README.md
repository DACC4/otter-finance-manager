# Otter Finance Manager

Django web app for tracking personal and shared finances: income, recurring expenses, saving buckets, and savings goals. A dashboard shows your monthly "fun money" left after all commitments.

## Features

- **Income** — track multiple income streams (monthly or annual)
- **Expenses** — recurring monthly or annual expenses, optionally shared with other users (split evenly)
- **Saving buckets** — fixed monthly savings pots (e.g. travel fund, car maintenance)
- **Savings goals** — target amount + deadline; calculates required monthly contribution
- **Dashboard** — summary of income, expenses, savings, and leftover fun money; filterable by tag
- **Tags** — color-coded labels to categorize any of the above
- **Site settings** — admin-configurable currency symbol/position and date display format

---

## Local development

**Requirements:** Python 3.12+, [`uv`](https://docs.astral.sh/uv/)

```bash
# 1. Install dependencies
uv sync

# Local runs need DEBUG on (or a DJANGO_SECRET_KEY); the app refuses to start otherwise
export DJANGO_DEBUG=1

# 2. Apply migrations
uv run python manage.py migrate

# 3. Create your user
uv run python manage.py createsuperuser

# 4. Start the dev server
uv run python manage.py runserver
```

Open http://127.0.0.1:8000 and log in with the credentials you just created.

---

## Docker

### Quick start with Docker Compose

```bash
# 1. Create a .env file with a secret key (required; compose refuses to start without it)
echo "DJANGO_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')" > .env

# 2. Build and start (PostgreSQL + gunicorn on port 8000)
docker compose up --build -d

# 3. Apply migrations
docker compose exec web python manage.py migrate

# 4. Create your user
docker compose exec web python manage.py createsuperuser
```

Open http://localhost:8000.

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `DJANGO_SECRET_KEY` | _(none)_ | **Required** unless `DJANGO_DEBUG` is on; startup fails without it |
| `DJANGO_DEBUG` | `False` | Set to `true` only for development |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated hostnames |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | _(empty)_ | **Required when behind a reverse proxy or HTTPS.** Comma-separated origins including scheme, e.g. `https://finance.example.com` |
| `DATABASE_URL` | SQLite | PostgreSQL URL, e.g. `postgres://user:pass@host:5432/db` (PostgreSQL 15+) |
| `DJANGO_HTTPS` | `False` | `true` makes session/CSRF cookies HTTPS-only. Enable when the site is served over HTTPS |
| `DJANGO_BEHIND_PROXY` | `False` | `true` trusts `X-Forwarded-Proto` from your reverse proxy. Only if the proxy always sets it |
| `DJANGO_HSTS_SECONDS` | `0` | Send HSTS for this many seconds (start small, e.g. `3600`; browsers cache it) |

### Using the published image

Docker images are published to the GitHub Container Registry on every push to `main` and on version tags.

```bash
# Pull the latest image from main
docker pull ghcr.io/<owner>/otter-finance-manager:main

# Or a specific release
docker pull ghcr.io/<owner>/otter-finance-manager:1.2.3
```

Example `docker-compose.yml` using the published image instead of building locally:

```yaml
services:
  db:
    image: postgres:15
    environment:
      POSTGRES_USER: otter
      POSTGRES_PASSWORD: otter
      POSTGRES_DB: otter
    volumes:
      - db-data:/var/lib/postgresql/data

  web:
    image: ghcr.io/<owner>/otter-finance-manager:main
    ports:
      - "8000:8000"
    environment:
      DJANGO_SECRET_KEY: "${DJANGO_SECRET_KEY:?Set DJANGO_SECRET_KEY in .env}"
      DATABASE_URL: "postgres://otter:otter@db:5432/otter"
      DJANGO_ALLOWED_HOSTS: "yourdomain.com"
      DJANGO_CSRF_TRUSTED_ORIGINS: "https://yourdomain.com"
      DJANGO_HTTPS: "true"
      DJANGO_BEHIND_PROXY: "true"
    depends_on:
      - db

volumes:
  db-data:
```

---

## Development commands

```bash
uv run python manage.py test          # Run tests
uv run ruff check .                   # Lint
uv run ruff format .                  # Format
uv run python manage.py makemigrations  # Generate migrations after model changes
```
