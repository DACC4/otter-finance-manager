from datetime import date
from decimal import Decimal

from django.test import TestCase

from finances.services import calculate_debts, calculate_financial_snapshot

from . import factories as f


class SnapshotDetailTests(TestCase):
    def setUp(self):
        self.alice = f.user("alice")
        self.bob = f.user("bob")

    def test_annual_expense_fields(self):
        f.annual_expense(self.alice, "1200", 3, shared_with=[self.bob])
        snap = calculate_financial_snapshot(self.alice, as_of=date(2025, 3, 10))
        self.assertEqual(snap["annual_withdrawals"], Decimal("600.00"))
        self.assertEqual(snap["annual_savings_balance"], Decimal("600.00"))
        self.assertEqual(snap["annual_monthly_saving"], Decimal("50.00"))
        self.assertEqual(snap["monthly_expenses"], Decimal("50.00"))

        later = calculate_financial_snapshot(self.alice, as_of=date(2025, 5, 10))
        self.assertEqual(later["annual_withdrawals"], Decimal(0))
        self.assertEqual(later["annual_savings_balance"], Decimal("100.00"))

    def test_thirteenth_month_to_bucket_reduces_bucket_need(self):
        travel = f.bucket(self.alice, "500")
        f.income(self.alice, "6000", months_per_year=13, thirteenth_month_bucket=travel)
        snap = calculate_financial_snapshot(self.alice, as_of=date(2025, 1, 1))
        self.assertEqual(snap["thirteenth_month_total"], Decimal(6000))
        self.assertEqual(
            snap["monthly_saving_buckets"], Decimal(0)
        )  # 500 - 500, floored
        self.assertEqual(snap["fun_money"], Decimal(6000))

    def test_thirteenth_month_partial_reduction(self):
        travel = f.bucket(self.alice, "800")
        f.income(self.alice, "1200", months_per_year=13, thirteenth_month_bucket=travel)
        snap = calculate_financial_snapshot(self.alice, as_of=date(2025, 1, 1))
        self.assertEqual(snap["monthly_saving_buckets"], Decimal("700.00"))

    def test_other_users_data_is_ignored(self):
        f.income(self.bob, "9999")
        f.expense(self.bob, "50")
        snap = calculate_financial_snapshot(self.alice, as_of=date(2025, 1, 1))
        self.assertEqual(snap["monthly_income"], Decimal(0))
        self.assertEqual(snap["monthly_expenses"], Decimal(0))


class DebtTests(TestCase):
    def setUp(self):
        self.alice = f.user("alice")
        self.bob = f.user("bob")
        self.carol = f.user("carol")

    def test_payer_is_owed_by_participants(self):
        f.expense(
            self.alice, "300", shared_with=[self.bob, self.carol], payer=self.alice
        )
        debts = calculate_debts(self.alice)
        self.assertEqual(
            debts["owed_to_me"],
            [
                (self.bob, Decimal("100.00"), Decimal("1200.00")),
                (self.carol, Decimal("100.00"), Decimal("1200.00")),
            ],
        )
        self.assertEqual(debts["i_owe"], [])
        self.assertEqual(
            calculate_debts(self.bob)["i_owe"],
            [(self.alice, Decimal("100.00"), Decimal("1200.00"))],
        )

    def test_bilateral_debts_are_netted(self):
        f.expense(
            self.alice, "300", shared_with=[self.bob], payer=self.alice
        )  # bob owes 150
        f.expense(
            self.bob, "100", name="Net", shared_with=[self.alice], payer=self.bob
        )  # alice owes 50
        self.assertEqual(
            calculate_debts(self.alice),
            {
                "owed_to_me": [(self.bob, Decimal("100.00"), Decimal("1200.00"))],
                "i_owe": [],
            },
        )
        self.assertEqual(
            calculate_debts(self.bob),
            {
                "owed_to_me": [],
                "i_owe": [(self.alice, Decimal("100.00"), Decimal("1200.00"))],
            },
        )

    def test_equal_debts_cancel_out(self):
        f.expense(self.alice, "100", shared_with=[self.bob], payer=self.alice)
        f.expense(self.bob, "100", name="b", shared_with=[self.alice], payer=self.bob)
        self.assertEqual(calculate_debts(self.alice), {"owed_to_me": [], "i_owe": []})

    def test_no_payer_means_no_debt(self):
        f.expense(self.alice, "100", shared_with=[self.bob])
        self.assertEqual(calculate_debts(self.bob), {"owed_to_me": [], "i_owe": []})
