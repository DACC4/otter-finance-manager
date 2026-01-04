# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
uv sync                                    # Install dependencies
uv run python manage.py migrate            # Apply migrations
uv run python manage.py createsuperuser    # Create admin user

# Development
uv run python manage.py runserver          # Start dev server (http://127.0.0.1:8000)
uv run python manage.py makemigrations    # Generate migrations after model changes

# Testing & Quality
uv run python manage.py test               # Run all tests
uv run python manage.py test finances      # Run tests for a specific app
uv run ruff check .                        # Lint
uv run ruff format .                       # Format

# Docker (production-like)
docker compose up --build                  # Build and start (PostgreSQL + gunicorn)
```

## Architecture

Django 5.1 app using `uv` as the package manager. SQLite in development, PostgreSQL in Docker via `dj-database-url` and the `DATABASE_URL` env var.

### Apps

- **`finances/`** — the sole Django app containing all models, views, forms, services, and tests
- **`otter_finance_manager/`** — Django project config (settings, root URLs, wsgi/asgi)

### Data flow

All financial calculations go through `finances/services.py:calculate_financial_snapshot(user, as_of)`. This is the central function called by `DashboardView` to compute the user's monthly picture. It returns a dict with: `monthly_income`, `monthly_expenses`, `monthly_saving_buckets`, `monthly_goal_need`, `fun_money`, `annual_withdrawals`, `annual_savings_balance`, `annual_monthly_saving`.

### Key model behaviors

- **`Expense.share_for(user)`** — returns a user's monthly share of an expense (0 if not a participant). Owner + `shared_with` users split evenly.
- **Annual expenses** have special handling: `target_month` sets when they're due; `monthly_annual_saving()` spreads the annual cost monthly; `expected_annual_balance()` tracks how much should be saved by now in the cycle.
- **`SavingsGoal.required_monthly_saving(as_of)`** — `(target - balance) / months_remaining`, floored at 1 month.
- **`Income.monthly_amount`** / **`Expense.monthly_amount`** — normalize annual amounts by dividing by 12.

### Views & permissions

All views require login (`LoginRequiredMixin`). Update/delete views use `OwnerCheckMixin` (a `UserPassesTestMixin`) to verify `obj.owner == request.user`. Create views use `OwnerCreateMixin` to auto-assign `owner = request.user`.

### Templates

`templates/base.html` is the single base template with global CSS and nav. All entity templates use `templates/finances/form.html` (generic create/edit) and `templates/finances/confirm_delete.html`. The dashboard is `templates/finances/dashboard.html`.

Custom template filter `share_for` is in `finances/templatetags/finances_extras.py` — used as `{{ expense|share_for:user }}`.

### Settings behavior

`settings.py` reads `DATABASE_URL` (via `dj-database-url`) for production PostgreSQL; falls back to SQLite. `DEBUG` and `SECRET_KEY` are read from environment variables in Docker.
