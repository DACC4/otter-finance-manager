from datetime import date
from decimal import Decimal

from django.test import TestCase

from finances.models import Frequency, SiteSettings

from . import factories as f


class IncomeTests(TestCase):
    def setUp(self):
        self.alice = f.user("alice")

    def test_monthly_income_is_its_amount(self):
        inc = f.income(self.alice, "4000")
        self.assertEqual(inc.monthly_amount, Decimal("4000"))
        self.assertEqual(inc.thirteenth_month_amount, Decimal("0"))

    def test_annual_income_is_spread_over_months_per_year(self):
        inc = f.income(self.alice, "52000", frequency=Frequency.ANNUAL, months_per_year=13)
        self.assertEqual(inc.monthly_amount, Decimal("4000.00"))
        self.assertEqual(inc.thirteenth_month_amount, Decimal("4000.00"))

    def test_annual_income_over_twelve_months(self):
        inc = f.income(self.alice, "1000", frequency=Frequency.ANNUAL)
        self.assertEqual(inc.monthly_amount, Decimal("83.33"))


class ExpenseShareTests(TestCase):
    def setUp(self):
        self.alice = f.user("alice")
        self.bob = f.user("bob")
        self.carol = f.user("carol")

    def test_unshared_expense_belongs_fully_to_owner(self):
        exp = f.expense(self.alice, "100")
        self.assertEqual(exp.participant_count, 1)
        self.assertEqual(exp.share_for(self.alice), Decimal("100.00"))
        self.assertEqual(exp.share_for(self.bob), Decimal("0"))

    def test_shared_expense_splits_evenly_and_rounds(self):
        exp = f.expense(self.alice, "100", shared_with=[self.bob, self.carol])
        self.assertEqual(exp.share_for(self.alice), Decimal("33.33"))
        self.assertEqual(exp.share_for(self.bob), Decimal("33.33"))
        self.assertEqual(list(exp.participants()), [self.alice, self.bob, self.carol])

    def test_annual_expense_monthly_share(self):
        exp = f.annual_expense(self.alice, "1200", 6, shared_with=[self.bob])
        self.assertEqual(exp.monthly_amount, Decimal("100.00"))
        self.assertEqual(exp.share_for(self.bob), Decimal("50.00"))
        self.assertEqual(exp.annual_share_for(self.bob), Decimal("600.00"))
        self.assertEqual(exp.monthly_annual_saving(self.bob), Decimal("50.00"))

    def test_annual_share_is_zero_for_non_participant_or_monthly(self):
        annual = f.annual_expense(self.alice, "1200", 6)
        monthly = f.expense(self.alice, "100")
        self.assertEqual(annual.annual_share_for(self.bob), Decimal("0"))
        self.assertEqual(annual.monthly_annual_saving(self.bob), Decimal("0"))
        self.assertEqual(monthly.annual_share_for(self.alice), Decimal("0"))

    def test_cycle_months_and_due_month(self):
        exp = f.annual_expense(self.alice, "1200", 3)
        self.assertEqual(exp.months_into_cycle(date(2025, 3, 15)), 12)
        self.assertEqual(exp.months_into_cycle(date(2025, 4, 1)), 1)
        self.assertEqual(exp.months_into_cycle(date(2025, 2, 1)), 11)
        self.assertTrue(exp.is_due_in_month(date(2025, 3, 1)))
        self.assertFalse(exp.is_due_in_month(date(2025, 4, 1)))

    def test_unset_target_month_defaults_to_december(self):
        exp = f.annual_expense(self.alice, "1200", None)
        self.assertTrue(exp.is_due_in_month(date(2025, 12, 1)))
        self.assertEqual(exp.months_into_cycle(date(2025, 1, 1)), 1)

    def test_expected_annual_balance(self):
        exp = f.annual_expense(self.alice, "1200", 3)
        self.assertEqual(exp.expected_annual_balance(self.alice, date(2025, 6, 1)), Decimal("300.00"))
        monthly = f.expense(self.alice, "100")
        self.assertEqual(monthly.expected_annual_balance(self.alice, date(2025, 6, 1)), Decimal("0"))


class SavingsGoalTests(TestCase):
    def setUp(self):
        self.alice = f.user("alice")

    def test_required_monthly_saving_divides_remaining_by_months(self):
        g = f.goal(self.alice, "3600", "600", target_date=date(2025, 7, 1))
        self.assertEqual(g.months_remaining(date(2025, 1, 1)), 6)
        self.assertEqual(g.required_monthly_saving(date(2025, 1, 1)), Decimal("500.00"))

    def test_past_or_same_month_target_needs_everything_now(self):
        past = f.goal(self.alice, "1000", "0", target_date=date(2024, 1, 1))
        same_month = f.goal(self.alice, "1000", "0", target_date=date(2025, 1, 20), name="b")
        self.assertEqual(past.months_remaining(date(2025, 1, 1)), 1)
        self.assertEqual(same_month.months_remaining(date(2025, 1, 1)), 1)
        self.assertEqual(past.required_monthly_saving(date(2025, 1, 1)), Decimal("1000.00"))

    def test_reached_goal_needs_nothing(self):
        g = f.goal(self.alice, "1000", "1500")
        self.assertEqual(g.required_monthly_saving(date(2025, 1, 1)), Decimal("0"))


class SiteSettingsTests(TestCase):
    def test_singleton(self):
        first = SiteSettings.get()
        SiteSettings(currency_symbol="€").save()
        self.assertEqual(SiteSettings.objects.count(), 1)
        self.assertEqual(SiteSettings.get().pk, first.pk)
        self.assertEqual(SiteSettings.get().currency_symbol, "€")
