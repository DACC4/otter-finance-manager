from decimal import Decimal
from typing import Dict

from django.db.models import Q
from django.utils import timezone

from .models import Expense, Frequency, Income, SavingBucket, SavingsGoal


def calculate_financial_snapshot(user, as_of=None) -> Dict[str, Decimal]:
    as_of = as_of or timezone.now().date()

    incomes = Income.objects.filter(owner=user)
    expenses = Expense.objects.filter(Q(owner=user) | Q(shared_with=user)).distinct()
    saving_buckets = SavingBucket.objects.filter(owner=user)
    savings_goals = SavingsGoal.objects.filter(owner=user)

    monthly_income = sum((income.monthly_amount for income in incomes), Decimal("0"))
    monthly_expenses = sum(
        (expense.share_for(user) for expense in expenses), Decimal("0")
    )
    monthly_saving_buckets = sum(
        (bucket.monthly_contribution for bucket in saving_buckets), Decimal("0")
    )
    # 13th-month incomes allocated to a bucket reduce the monthly saving needed,
    # since one annual lump sum covers thirteenth_month_amount / 12 per month.
    bucket_thirteenth_reduction = sum(
        (
            (income.thirteenth_month_amount / Decimal("12")).quantize(Decimal("0.01"))
            for income in incomes
            if income.thirteenth_month_bucket_id is not None
        ),
        Decimal("0"),
    )
    monthly_saving_buckets = max(
        monthly_saving_buckets - bucket_thirteenth_reduction, Decimal("0")
    )
    monthly_goal_need = sum(
        (goal.required_monthly_saving(as_of) for goal in savings_goals), Decimal("0")
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
        Decimal("0"),
    )
    annual_savings_balance = sum(
        (expense.expected_annual_balance(user, as_of) for expense in annual_expenses),
        Decimal("0"),
    )
    annual_monthly_saving = sum(
        (expense.monthly_annual_saving(user) for expense in annual_expenses),
        Decimal("0"),
    )

    thirteenth_month_total = sum(
        (income.thirteenth_month_amount for income in incomes),
        Decimal("0"),
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
