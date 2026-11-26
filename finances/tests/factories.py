from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model

from finances.models import Expense, Frequency, Income, SavingBucket, SavingsGoal, Tag


def user(username):
    return get_user_model().objects.create_user(username=username, password="pass1234")


def income(owner, amount, name="Salary", **kwargs):
    return Income.objects.create(owner=owner, name=name, amount=Decimal(amount), **kwargs)


def expense(owner, amount, name="Rent", shared_with=(), **kwargs):
    exp = Expense.objects.create(owner=owner, name=name, amount=Decimal(amount), **kwargs)
    exp.shared_with.add(*shared_with)
    return exp


def annual_expense(owner, amount, target_month, name="Insurance", shared_with=()):
    return expense(
        owner,
        amount,
        name=name,
        shared_with=shared_with,
        frequency=Frequency.ANNUAL,
        target_month=target_month,
    )


def bucket(owner, contribution, name="Travel"):
    return SavingBucket.objects.create(
        owner=owner, name=name, monthly_contribution=Decimal(contribution)
    )


def goal(owner, target, balance, target_date=date(2025, 7, 1), name="Laptop"):
    return SavingsGoal.objects.create(
        owner=owner,
        name=name,
        target_amount=Decimal(target),
        current_balance=Decimal(balance),
        target_date=target_date,
    )


def tag(owner, name="Home", color="#112233"):
    return Tag.objects.create(owner=owner, name=name, color=color)
