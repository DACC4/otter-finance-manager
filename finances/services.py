from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.utils import timezone

from .models import (
    Expense,
    Frequency,
    Income,
    SavingBucket,
    SavingsGoal,
)

CENT = Decimal("0.01")


def _monthly_cover(incomes, target_field: str) -> dict[int, Decimal]:
    """Sum thirteenth_month_amount / 12 per allocation target id."""
    cover: dict[int, Decimal] = defaultdict(Decimal)
    for income in incomes:
        target_id = getattr(income, target_field)
        if target_id is not None:
            cover[target_id] += (income.thirteenth_month_amount / Decimal(12)).quantize(
                CENT
            )
    return dict(cover)


@dataclass(frozen=True)
class ThirteenthMonthCover:
    """Monthly amounts a user's 13th-month lump sums cover, per bucket/expense.

    One annual payment covers thirteenth_month_amount / 12 per month of the
    bucket or expense it is allocated to. A cover only reduces its own target,
    never below 0, and only for the income owner (other participants of a
    shared expense keep their full share).
    """

    buckets: dict[int, Decimal] = field(default_factory=dict)
    expenses: dict[int, Decimal] = field(default_factory=dict)

    @classmethod
    def from_incomes(cls, incomes) -> "ThirteenthMonthCover":
        return cls(
            buckets=_monthly_cover(incomes, "thirteenth_month_bucket_id"),
            expenses=_monthly_cover(incomes, "thirteenth_month_expense_id"),
        )

    def bucket_need(self, bucket) -> Decimal:
        """What the user still puts into the bucket each month."""
        cover = self.buckets.get(bucket.pk, Decimal(0))
        return max(bucket.monthly_contribution - cover, Decimal(0))

    def expense_share(self, expense, user) -> Decimal:
        """User's monthly share still paid from regular income."""
        cover = self.expenses.get(expense.pk, Decimal(0))
        return max(expense.share_for(user) - cover, Decimal(0))

    def annual_saving(self, expense, user) -> Decimal:
        """Monthly amount still set aside for an annual bill."""
        cover = self.expenses.get(expense.pk, Decimal(0))
        return max(expense.monthly_annual_saving(user) - cover, Decimal(0))


def calculate_financial_snapshot(user, as_of=None) -> dict[str, Decimal]:
    as_of = as_of or timezone.localdate()

    incomes = Income.objects.filter(owner=user)
    expenses = Expense.objects.visible_to(user)
    saving_buckets = SavingBucket.objects.filter(owner=user)
    savings_goals = SavingsGoal.objects.filter(owner=user)

    monthly_income = sum((income.monthly_amount for income in incomes), Decimal(0))
    cover = ThirteenthMonthCover.from_incomes(incomes)
    monthly_expenses = sum(
        (cover.expense_share(expense, user) for expense in expenses), Decimal(0)
    )
    monthly_saving_buckets = sum(
        (cover.bucket_need(b) for b in saving_buckets), Decimal(0)
    )
    monthly_goal_need = sum(
        (goal.required_monthly_saving(as_of) for goal in savings_goals), Decimal(0)
    )

    annual_expenses = [
        expense for expense in expenses if expense.frequency == Frequency.ANNUAL
    ]
    annual_withdrawals = sum(
        (
            expense.annual_share_for(user)
            for expense in annual_expenses
            if expense.is_due_in_month(as_of)
        ),
        Decimal(0),
    )
    annual_savings_balance = sum(
        (expense.expected_annual_balance(user, as_of) for expense in annual_expenses),
        Decimal(0),
    )
    annual_monthly_saving = sum(
        (cover.annual_saving(expense, user) for expense in annual_expenses),
        Decimal(0),
    )

    thirteenth_month_total = sum(
        (income.thirteenth_month_amount for income in incomes),
        Decimal(0),
    )

    committed = monthly_expenses + monthly_saving_buckets + monthly_goal_need
    fun_money = monthly_income - committed

    return {
        "monthly_income": monthly_income,
        "monthly_expenses": monthly_expenses,
        "monthly_saving_buckets": monthly_saving_buckets,
        "monthly_goal_need": monthly_goal_need,
        # Allow negative leftover (user may overspend)
        "fun_money": fun_money,
        "annual_withdrawals": annual_withdrawals,
        "annual_savings_balance": annual_savings_balance,
        "annual_monthly_saving": annual_monthly_saving,
        "thirteenth_month_total": thirteenth_month_total,
    }


def calculate_debts(user) -> dict[str, list[tuple]]:
    """
    Returns debts involving `user` based on expenses where payer is set.

    Returns:
        {
            "owed_to_me":  [(other_user, monthly, yearly), ...],
            "i_owe":       [(other_user, monthly, yearly), ...],
        }
    """
    # All expenses with a payer where this user is involved
    payer_expenses = Expense.objects.visible_to(user).filter(payer__isnull=False)

    owed_to_me: dict = defaultdict(Decimal)
    i_owe: dict = defaultdict(Decimal)

    for expense in payer_expenses:
        if expense.payer == user:
            # Others owe me their share
            for participant in expense.participants():
                if participant != user:
                    owed_to_me[participant] += expense.share_for(participant)
        else:
            # I owe the payer my share
            my_share = expense.share_for(user)
            if my_share > 0:
                i_owe[expense.payer] += my_share

    # Net out bilateral debts: only show the direction of the larger side
    all_parties = set(owed_to_me) | set(i_owe)
    net_owed_to_me = {}
    net_i_owe = {}
    for party in all_parties:
        net = owed_to_me.get(party, Decimal(0)) - i_owe.get(party, Decimal(0))
        if net > 0:
            net_owed_to_me[party] = net
        elif net < 0:
            net_i_owe[party] = -net

    return {
        "owed_to_me": [
            (other, monthly, (monthly * 12).quantize(Decimal("0.01")))
            for other, monthly in sorted(
                net_owed_to_me.items(), key=lambda x: x[0].username
            )
        ],
        "i_owe": [
            (other, monthly, (monthly * 12).quantize(Decimal("0.01")))
            for other, monthly in sorted(net_i_owe.items(), key=lambda x: x[0].username)
        ],
    }


# ── Dashboard building blocks ─────────────────────────────────────────────

SORT_OPTIONS = {"price_desc": True, "price_asc": False}  # option -> reverse


def value_rows(items, value) -> list[dict]:
    """Bar-chart rows: one {"name", "value"} per item."""
    return [{"name": item.name, "value": value(item)} for item in items]


def need_rows(items, full, need) -> list[dict]:
    """Rows showing what is still needed; "covered" when a 13th month pays part."""
    rows = value_rows(items, need)
    for item, row in zip(items, rows, strict=True):
        covered = full(item) - row["value"]
        if covered > 0:
            row["covered"] = covered
    return rows


def sort_rows(rows: list[dict], sort_option: str) -> list[dict]:
    """Sort by value for a known option; any other option keeps the given order."""
    if sort_option not in SORT_OPTIONS:
        return rows
    return sorted(rows, key=lambda row: row["value"], reverse=SORT_OPTIONS[sort_option])


def max_value(rows: list[dict]) -> Decimal:
    """Largest value, used as the 100% bar width; 1 when empty to avoid dividing by 0."""
    return max((row["value"] for row in rows), default=Decimal(1))


def total_value(rows: list[dict]) -> Decimal:
    return sum((row["value"] for row in rows), Decimal(0))


def expense_split_totals(expenses, share) -> dict[str, Decimal]:
    """User's share (share(expense)) by frequency and shared vs. not shared."""
    totals = {
        f"{frequency}_{kind}_total": Decimal(0)
        for frequency in ("monthly", "annual")
        for kind in ("shared", "non_shared")
    }
    for expense in expenses:
        frequency = "annual" if expense.frequency == Frequency.ANNUAL else "monthly"
        kind = "shared" if expense.participant_count > 1 else "non_shared"
        totals[f"{frequency}_{kind}_total"] += share(expense)
    totals["combined_total"] = sum(totals.values(), Decimal(0))
    return totals


def goal_progress(goal, as_of) -> dict:
    percent = (
        goal.current_balance / goal.target_amount * Decimal(100)
        if goal.target_amount
        else Decimal(0)
    )
    return {
        "id": goal.pk,
        "name": goal.name,
        "current": goal.current_balance,
        "target": goal.target_amount,
        "percent": percent.quantize(CENT),
        "required_monthly": goal.required_monthly_saving(as_of),
    }


def tag_expense_rows(tags, expenses, user, share) -> list[dict]:
    """Per-tag sum of the user's share of the expenses they tagged with it."""
    totals: dict[int, Decimal] = defaultdict(Decimal)
    for expense in expenses:
        for tag in expense.tags_of(user):
            totals[tag.id] += share(expense)
    return [
        {"id": tag.id, "name": tag.name, "value": totals[tag.id], "color": tag.color}
        for tag in tags
        if totals[tag.id] > 0
    ]
