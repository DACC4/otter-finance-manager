from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Expense, Frequency, Income, SavingBucket, SavingsGoal
from .services import calculate_financial_snapshot


class SnapshotTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user(username="alice", password="pass1234")
        self.bob = User.objects.create_user(username="bob", password="pass1234")

    def test_snapshot_shared_expenses_and_goals(self):
        as_of = date(2025, 1, 1)
        Income.objects.create(
            owner=self.alice, name="Salary", amount=4000, frequency=Frequency.MONTHLY
        )
        shared_expense = Expense.objects.create(
            owner=self.alice,
            name="Rent",
            amount=1200,
            frequency=Frequency.MONTHLY,
        )
        shared_expense.shared_with.add(self.bob)

        Expense.objects.create(
            owner=self.alice,
            name="Phone",
            amount=200,
            frequency=Frequency.MONTHLY,
        )

        SavingBucket.objects.create(
            owner=self.alice, name="Travel", monthly_contribution=300
        )

        SavingsGoal.objects.create(
            owner=self.alice,
            name="Laptop",
            target_amount=3600,
            current_balance=600,
            target_date=date(2025, 7, 1),
        )

        snapshot = calculate_financial_snapshot(self.alice, as_of=as_of)
        self.assertEqual(snapshot["monthly_income"], 4000)
        # shared rent split between 2 people => 600
        self.assertEqual(snapshot["monthly_expenses"], 800)  # 600 rent + 200 phone
        self.assertEqual(snapshot["monthly_saving_buckets"], 300)
        self.assertEqual(snapshot["monthly_goal_need"], 500)  # (3600-600)/6 months
        self.assertEqual(snapshot["fun_money"], 2400)

        bob_snapshot = calculate_financial_snapshot(self.bob, as_of=as_of)
        self.assertEqual(bob_snapshot["monthly_expenses"], 600)
        self.assertEqual(bob_snapshot["fun_money"], -600)
