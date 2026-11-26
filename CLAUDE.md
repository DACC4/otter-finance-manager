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

`services.py` also holds the dashboard building blocks (`value_rows`, `need_rows`, `sort_rows`, `max_value`, `total_value`, `expense_split_totals`, `goal_progress`, `tag_expense_rows`) and the 13th-month rule, `ThirteenthMonthCover.from_incomes(incomes)`: a 13th month allocated to a bucket or an expense covers `thirteenth_month_amount / 12` per month of that target only, floored at 0, and for a shared expense only the income owner's share. `calculate_debts` deliberately uses the real share (your 13th month doesn't pay the payer). Dashboard bars show the effective amount with a "13th month covers" note, so bar totals equal the cards. Coverage always comes from all incomes, even under a tag filter. Keep calculations there, not in views.

Dates: always `timezone.localdate()` (never `timezone.now().date()`, which is the UTC date); `TIME_ZONE` comes from `DJANGO_TIME_ZONE` (default `Europe/Zurich`). The dashboard passes its `as_of` to the snapshot so one date drives the page.

### Input boundary

`finances/parsing.py` parses untrusted request input once: `parse_bulk_tags_payload` (bulk-tag JSON; raises `InvalidPayload`, returned as 400), `parse_owned_tag_id` (dashboard `?tag=`, only the user's own tags), and `client_ip_behind_proxy` (right-most `X-Forwarded-For` entry, used by login throttling when `DJANGO_BEHIND_PROXY` is on). Code past the boundary trusts these values.

### Key model behaviors

- **`Expense.objects.visible_to(user)`** — the one query for expenses a user owns or shares in. It preloads owner, payer, `shared_with` and the user's own tag links; per-row code must read those (`has_participant` checks `shared_with.all()`, `tags_of(user)` reads the prefetched links) so page cost stays constant (`QueryCountTests`). **`Expense.has_participant(user)`** — owner or in `shared_with`.
- **`Expense.target_month`** has month `choices` (1–12); show it with `get_target_month_display`.
- **`Expense.share_for(user)`** — returns a user's monthly share of an expense (0 if not a participant). Owner + `shared_with` users split evenly.
- **`Expense.payer`** must be a participant (enforced in `ExpenseForm.clean`); the owner is never offered in `shared_with`.
- **Annual expenses** have special handling: `target_month` sets when they're due; `monthly_annual_saving()` spreads the annual cost monthly; `expected_annual_balance()` tracks how much should be saved by now in the cycle.
- **`SavingsGoal.required_monthly_saving(as_of)`** — `(target - balance) / months_remaining`, floored at 1 month.
- **`Income.monthly_amount`** / **`Expense.monthly_amount`** — normalize annual amounts by dividing by 12.

### Views & permissions

All views require login (`LoginRequiredMixin`). Update/delete views use `OwnerCheckMixin` (a `UserPassesTestMixin`) to verify `obj.owner == request.user`; `ExpenseUpdateView` also lets participants edit. Create views use `OwnerCreateMixin` to auto-assign `owner = request.user`. Shared mixins: `UserFormKwargsMixin` (passes `user` to forms so choices are scoped), `OwnedListMixin` (owner-filtered list querysets), `UserTagsContextMixin` (`user_tags` for the bulk-tag toolbar), `SavedMessageMixin` ("Saved" messages), `OwnerDeleteMixin` (owner-only delete + "Deleted" message). Update views set `delete_url_name`; the edit page shows Delete only to the owner. Forms: the shared form mixin labels every choice with `display_name` (people by full name) and renders `tags`/`shared_with` as checkboxes.

Logout must be a POST (Django 5+); the nav uses a small form. `/healthz` is answered by `finances.middleware.HealthCheckMiddleware`, first in `MIDDLEWARE` so it works before host validation (used by the Dockerfile `HEALTHCHECK`). Login is throttled by django-axes (5 failures per username+IP → 15 min lock, HTTP 429); tests must use `force_login`, since `client.login()` doesn't pass the request axes needs.

### Templates

`templates/base.html` is the single base template with global CSS and nav. All entity templates use `templates/finances/form.html` (generic create/edit) and `templates/finances/confirm_delete.html`. The dashboard is `templates/finances/dashboard.html`.

Custom template filter `share_for` is in `finances/templatetags/finances_extras.py` — used as `{{ expense|share_for:user }}`. Layout must work at 390px wide: list tables sit in `.table-card`, dashboard tables in `.table-scroll`, and the nav becomes a scrollable row below 760px.

### Settings behavior

`settings.py` reads `DATABASE_URL` (via `dj-database-url`) for production PostgreSQL; falls back to SQLite. `DJANGO_SECRET_KEY` is mandatory unless `DJANGO_DEBUG` is on or tests are running. HTTPS hardening is opt-in via `DJANGO_HTTPS`, `DJANGO_BEHIND_PROXY` and `DJANGO_HSTS_SECONDS`; `DJANGO_TIME_ZONE` sets the local time zone (see README).
