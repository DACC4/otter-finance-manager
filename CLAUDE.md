# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Without `DJANGO_SECRET_KEY`, settings refuse to load unless `DJANGO_DEBUG=1` (test runs are exempt), so export it for local work:

```bash
export DJANGO_DEBUG=1

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
uv run pytest -q                           # Same suite via pytest-django (used by crapper/mutator)
uv run ruff check .                        # Lint
uv run ruff format .                       # Format

# Docker (production-like)
docker compose up --build                  # Build and start (PostgreSQL + gunicorn)
```

## Architecture

Django 6.1 app (Python 3.12+, PostgreSQL 15+) using `uv` as the package manager. SQLite in development, PostgreSQL in Docker via `dj-database-url` and the `DATABASE_URL` env var.

### Apps

- **`finances/`** — the sole Django app containing all models, views, forms, services, and tests (`finances/tests/`, with shared builders in `tests/factories.py`)
- **`otter_finance_manager/`** — Django project config (settings, root URLs, wsgi/asgi)

### Data flow

All financial calculations go through `finances/services.py:calculate_financial_snapshot(user, as_of)`. This is the central function called by `DashboardView` to compute the user's monthly picture. It returns a dict with: `monthly_income`, `monthly_expenses`, `monthly_saving_buckets`, `monthly_goal_need`, `fun_money`, `annual_withdrawals`, `annual_savings_balance`, `annual_monthly_saving`, `thirteenth_month_total`.

`services.py` also holds the dashboard building blocks (`value_rows`, `sort_rows`, `max_value`, `total_value`, `expense_split_totals`, `goal_progress`, `tag_expense_rows`) and the 13th-month rule (`thirteenth_month_bucket_reductions`, `effective_bucket_contribution`: a reduction applies to its own bucket only, floored at 0). Keep calculations there, not in views.

### Input boundary

`finances/parsing.py` parses untrusted request input once: `parse_bulk_tags_payload` (bulk-tag JSON; raises `InvalidPayload`, returned as 400) and `parse_owned_tag_id` (dashboard `?tag=`, only the user's own tags). Code past the boundary trusts these values.

### Key model behaviors

- **`Expense.objects.visible_to(user)`** — the one query for expenses a user owns or shares in. **`Expense.has_participant(user)`** — owner or in `shared_with`.
- **`Expense.share_for(user)`** — returns a user's monthly share of an expense (0 if not a participant). Owner + `shared_with` users split evenly.
- **`Expense.payer`** must be a participant (enforced in `ExpenseForm.clean`); the owner is never offered in `shared_with`.
- **Annual expenses** have special handling: `target_month` sets when they're due; `monthly_annual_saving()` spreads the annual cost monthly; `expected_annual_balance()` tracks how much should be saved by now in the cycle.
- **`SavingsGoal.required_monthly_saving(as_of)`** — `(target - balance) / months_remaining`, floored at 1 month.
- **`Income.monthly_amount`** / **`Expense.monthly_amount`** — normalize annual amounts by dividing by 12.

### Views & permissions

All views require login (`LoginRequiredMixin`). Update/delete views use `OwnerCheckMixin` (a `UserPassesTestMixin`) to verify `obj.owner == request.user`; `ExpenseUpdateView` also lets participants edit. Create views use `OwnerCreateMixin` to auto-assign `owner = request.user`. Shared mixins: `UserFormKwargsMixin` (passes `user` to forms so choices are scoped), `OwnedListMixin` (owner-filtered list querysets), `UserTagsContextMixin` (`user_tags` for the bulk-tag toolbar).

### Templates

`templates/base.html` is the single base template with global CSS and nav. All entity templates use `templates/finances/form.html` (generic create/edit) and `templates/finances/confirm_delete.html`. The dashboard is `templates/finances/dashboard.html`.

Custom template filter `share_for` is in `finances/templatetags/finances_extras.py` — used as `{{ expense|share_for:user }}`.

### Settings behavior

`settings.py` reads `DATABASE_URL` (via `dj-database-url`) for production PostgreSQL; falls back to SQLite. `DJANGO_SECRET_KEY` is mandatory unless `DJANGO_DEBUG` is on or tests are running. HTTPS hardening is opt-in via `DJANGO_HTTPS`, `DJANGO_BEHIND_PROXY` and `DJANGO_HSTS_SECONDS` (see README).
