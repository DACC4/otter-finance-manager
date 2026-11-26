import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from finances.models import (
    Expense,
    Income,
    SavingBucket,
    SavingsGoal,
    Tag,
    UserExpenseTag,
)

from . import factories as f


class LoggedInTestCase(TestCase):
    def setUp(self):
        self.alice = f.user("alice")
        self.bob = f.user("bob")
        self.client.force_login(self.alice)


class AuthTests(TestCase):
    def test_pages_require_login(self):
        for name in [
            "dashboard",
            "income_list",
            "expense_list",
            "bucket_list",
            "goal_list",
            "tag_list",
        ]:
            response = self.client.get(reverse(f"finances:{name}"))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn(reverse("login"), response["Location"])

    def test_bulk_tags_requires_login_with_json_403(self):
        response = self.client.post(
            reverse("finances:income_bulk_tags"), "{}", content_type="application/json"
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["ok"], False)


class DashboardTests(LoggedInTestCase):
    def test_dashboard_context(self):
        home = f.tag(self.alice, "Home")
        f.income(self.alice, "4000")
        rent = f.expense(self.alice, "1200", shared_with=[self.bob])
        f.expense(self.alice, "200", name="Phone")
        f.annual_expense(self.alice, "1200", date.today().month, name="Insurance")
        UserExpenseTag.objects.create(user=self.alice, expense=rent, tag=home)
        f.bucket(self.alice, "300")
        f.goal(
            self.alice, "1000", "250", target_date=date.today() + timedelta(days=400)
        )
        f.goal(
            self.alice,
            "0",
            "0",
            name="Zero",
            target_date=date.today() + timedelta(days=400),
        )

        response = self.client.get(reverse("finances:dashboard"))
        self.assertEqual(response.status_code, 200)
        ctx = response.context
        self.assertEqual(ctx["monthly_shared_total"], Decimal("600.00"))
        self.assertEqual(ctx["monthly_non_shared_total"], Decimal("200.00"))
        self.assertEqual(ctx["annual_non_shared_total"], Decimal("100.00"))
        self.assertEqual(ctx["combined_total"], Decimal("900.00"))
        self.assertEqual(
            [r["name"] for r in ctx["expenses_data"]], ["Rent", "Phone", "Insurance"]
        )
        self.assertEqual(ctx["expenses_max"], Decimal("600.00"))
        self.assertEqual(ctx["incomes_total"], Decimal(4000))
        self.assertEqual(ctx["buckets_total"], Decimal(300))
        self.assertEqual([e.name for e in ctx["annual_due_expenses"]], ["Insurance"])
        self.assertEqual(
            ctx["tag_expense_data"],
            [
                {
                    "id": home.id,
                    "name": "Home",
                    "value": Decimal("600.00"),
                    "color": "#112233",
                }
            ],
        )
        self.assertEqual(ctx["tag_expense_max"], Decimal("600.00"))
        percents = {g["name"]: g["percent"] for g in ctx["savings_goals"]}
        self.assertEqual(
            percents, {"Laptop": Decimal("25.00"), "Zero": Decimal("0.00")}
        )
        self.assertFalse(ctx["fun_negative"])

    def test_dashboard_sort_ascending(self):
        f.expense(self.alice, "200", name="Phone")
        f.expense(self.alice, "50", name="Water")
        f.expense(self.alice, "100", name="Gas")
        ctx = self.client.get(
            reverse("finances:dashboard"), {"sort": "price_asc"}
        ).context
        self.assertEqual(
            [r["name"] for r in ctx["expenses_data"]], ["Water", "Gas", "Phone"]
        )
        ctx = self.client.get(reverse("finances:dashboard"), {"sort": "none"}).context
        self.assertEqual(
            [r["name"] for r in ctx["expenses_data"]], ["Gas", "Phone", "Water"]
        )

    def test_dashboard_tag_filter(self):
        home = f.tag(self.alice, "Home")
        rent = f.expense(self.alice, "1200")
        f.expense(self.alice, "200", name="Phone")
        tagged_income = f.income(self.alice, "4000")
        tagged_income.tags.add(home)
        f.income(self.alice, "100", name="Side")
        UserExpenseTag.objects.create(user=self.alice, expense=rent, tag=home)
        response = self.client.get(reverse("finances:dashboard"), {"tag": str(home.id)})
        ctx = response.context
        self.assertEqual([r["name"] for r in ctx["expenses_data"]], ["Rent"])
        self.assertEqual([r["name"] for r in ctx["incomes_data"]], ["Salary"])
        self.assertContains(response, f'<option value="{home.id}" selected')

    def test_negative_fun_money_flag(self):
        f.expense(self.alice, "100")
        self.assertTrue(
            self.client.get(reverse("finances:dashboard")).context["fun_negative"]
        )


class PermissionTests(LoggedInTestCase):
    def test_lists_only_show_own_or_shared_items(self):
        f.income(self.bob, "1", name="Bob income")
        f.expense(self.bob, "1", name="Bob private")
        f.expense(self.bob, "1", name="Bob shared", shared_with=[self.alice])
        incomes = self.client.get(reverse("finances:income_list")).context["incomes"]
        expenses = self.client.get(reverse("finances:expense_list")).context["expenses"]
        self.assertEqual(list(incomes), [])
        self.assertEqual([e.name for e in expenses], ["Bob shared"])

    def test_cannot_edit_or_delete_other_users_items(self):
        inc = f.income(self.bob, "1")
        tag = f.tag(self.bob)
        g = f.goal(self.bob, "1", "0")
        b = f.bucket(self.bob, "1")
        exp = f.expense(self.bob, "1")
        for name, pk in [
            ("income", inc.pk),
            ("tag", tag.pk),
            ("goal", g.pk),
            ("bucket", b.pk),
            ("expense", exp.pk),
        ]:
            for action in ["edit", "delete"]:
                response = self.client.get(
                    reverse(f"finances:{name}_{action}", args=[pk])
                )
                self.assertEqual(response.status_code, 403, f"{name}_{action}")
        self.client.post(reverse("finances:income_delete", args=[inc.pk]))
        self.assertTrue(Income.objects.filter(pk=inc.pk).exists())

    def test_participant_can_edit_but_not_delete_shared_expense(self):
        exp = f.expense(self.bob, "100", shared_with=[self.alice])
        self.assertEqual(
            self.client.get(
                reverse("finances:expense_edit", args=[exp.pk])
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                reverse("finances:expense_delete", args=[exp.pk])
            ).status_code,
            403,
        )


class CrudTests(LoggedInTestCase):
    def test_create_income_assigns_owner(self):
        response = self.client.post(
            reverse("finances:income_add"),
            {
                "name": "Job",
                "amount": "5000",
                "frequency": "monthly",
                "months_per_year": "12",
            },
        )
        self.assertRedirects(response, reverse("finances:income_list"))
        self.assertEqual(Income.objects.get().owner, self.alice)

    def test_income_cannot_assign_13th_to_bucket_and_expense(self):
        b = f.bucket(self.alice, "100")
        exp = f.expense(self.alice, "100")
        response = self.client.post(
            reverse("finances:income_add"),
            {
                "name": "Job",
                "amount": "5000",
                "frequency": "monthly",
                "months_per_year": "13",
                "thirteenth_month_bucket": b.pk,
                "thirteenth_month_expense": exp.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Income.objects.exists())

    def test_income_form_offers_only_own_tags_and_buckets(self):
        mine = f.tag(self.alice, "Mine")
        f.tag(self.bob, "Theirs")
        my_bucket = f.bucket(self.alice, "1")
        f.bucket(self.bob, "1", name="Bob bucket")
        form = self.client.get(reverse("finances:income_add")).context["form"]
        self.assertEqual(list(form.fields["tags"].queryset), [mine])
        self.assertEqual(
            list(form.fields["thirteenth_month_bucket"].queryset), [my_bucket]
        )

    def test_create_expense_with_personal_tags(self):
        home = f.tag(self.alice, "Home")
        response = self.client.post(
            reverse("finances:expense_add"),
            {
                "name": "Rent",
                "amount": "1000",
                "frequency": "monthly",
                "shared_with": [self.bob.pk],
                "tags": [home.pk],
            },
        )
        self.assertRedirects(response, reverse("finances:expense_list"))
        exp = Expense.objects.get()
        self.assertEqual(exp.owner, self.alice)
        self.assertEqual(list(exp.shared_with.all()), [self.bob])
        self.assertEqual(
            list(UserExpenseTag.objects.values_list("user", "tag")),
            [(self.alice.pk, home.pk)],
        )

    def test_expense_form_shared_with_excludes_self(self):
        form = self.client.get(reverse("finances:expense_add")).context["form"]
        self.assertEqual(list(form.fields["shared_with"].queryset), [self.bob])

    def test_edit_expense_payer_limited_to_participants(self):
        carol = f.user("carol")
        exp = f.expense(self.alice, "100", shared_with=[self.bob])
        form = self.client.get(reverse("finances:expense_edit", args=[exp.pk])).context[
            "form"
        ]
        self.assertEqual(set(form.fields["payer"].queryset), {self.alice, self.bob})
        self.assertNotIn(carol, form.fields["payer"].queryset)

    def test_edit_expense_shows_and_replaces_my_tags(self):
        home, work = f.tag(self.alice, "Home"), f.tag(self.alice, "Work")
        exp = f.expense(self.alice, "100")
        UserExpenseTag.objects.create(user=self.alice, expense=exp, tag=home)
        form = self.client.get(reverse("finances:expense_edit", args=[exp.pk])).context[
            "form"
        ]
        self.assertEqual(list(form.initial["tags"]), [home])
        self.client.post(
            reverse("finances:expense_edit", args=[exp.pk]),
            {
                "name": "Rent",
                "amount": "100",
                "frequency": "monthly",
                "tags": [work.pk],
            },
        )
        self.assertEqual(
            list(UserExpenseTag.objects.values_list("tag", flat=True)), [work.pk]
        )

    def test_create_bucket_goal_tag_and_delete(self):
        self.client.post(
            reverse("finances:bucket_add"), {"name": "B", "monthly_contribution": "10"}
        )
        self.client.post(
            reverse("finances:goal_add"),
            {
                "name": "G",
                "target_amount": "10",
                "target_date": "2030-01-01",
                "current_balance": "0",
            },
        )
        self.client.post(reverse("finances:tag_add"), {"name": "T", "color": "#000000"})
        self.assertEqual(SavingBucket.objects.get().owner, self.alice)
        self.assertEqual(SavingsGoal.objects.get().owner, self.alice)
        tag = Tag.objects.get()
        self.assertRedirects(
            self.client.post(reverse("finances:tag_delete", args=[tag.pk])),
            reverse("finances:tag_list"),
        )
        self.assertFalse(Tag.objects.exists())

    def test_list_views_render(self):
        home = f.tag(self.alice, "Home")
        f.income(self.alice, "100").tags.add(home)
        f.goal(self.alice, "100", "0")
        f.expense(self.alice, "100", payer=self.alice, shared_with=[self.bob])
        for name in [
            "income_list",
            "expense_list",
            "bucket_list",
            "goal_list",
            "tag_list",
        ]:
            response = self.client.get(reverse(f"finances:{name}"))
            self.assertEqual(response.status_code, 200, name)
        f.tag(self.bob, "Not mine")
        for name in ["income_list", "expense_list", "bucket_list", "goal_list"]:
            ctx = self.client.get(reverse(f"finances:{name}")).context
            self.assertEqual(
                ctx["user_tags"],
                [{"id": home.id, "name": "Home", "color": "#112233"}],
                name,
            )

    def test_bucket_list_shows_thirteenth_month_reduction(self):
        travel = f.bucket(self.alice, "800")
        f.income(self.alice, "1200", months_per_year=13, thirteenth_month_bucket=travel)
        ctx = self.client.get(reverse("finances:bucket_list")).context
        self.assertEqual(ctx["bucket_reductions"], {travel.pk: Decimal("100.00")})
        self.assertEqual(ctx["bucket_effective"], {travel.pk: Decimal("700.00")})


class BulkTagsTests(LoggedInTestCase):
    def post(self, name, payload):
        body = payload if isinstance(payload, str) else json.dumps(payload)
        return self.client.post(
            reverse(f"finances:{name}"), body, content_type="application/json"
        )

    def test_add_remove_set_on_owned_items(self):
        a, b = f.tag(self.alice, "A"), f.tag(self.alice, "B")
        inc = f.income(self.alice, "1")
        other = f.income(self.bob, "1", name="Bob")
        response = self.post(
            "income_bulk_tags",
            {"action": "add", "item_ids": [inc.pk, other.pk], "tag_ids": [a.pk, b.pk]},
        )
        self.assertEqual(response.json(), {"ok": True, "updated": 1})
        self.assertEqual(set(inc.tags.all()), {a, b})
        self.assertEqual(list(other.tags.all()), [])
        self.post(
            "income_bulk_tags",
            {"action": "remove", "item_ids": [inc.pk], "tag_ids": [a.pk]},
        )
        self.assertEqual(list(inc.tags.all()), [b])
        self.post(
            "income_bulk_tags",
            {"action": "set", "item_ids": [inc.pk], "tag_ids": [a.pk]},
        )
        self.assertEqual(list(inc.tags.all()), [a])

    def test_foreign_tags_are_ignored(self):
        bob_tag = f.tag(self.bob, "Bob")
        g = f.goal(self.alice, "1", "0")
        self.post(
            "goal_bulk_tags",
            {"action": "add", "item_ids": [g.pk], "tag_ids": [bob_tag.pk]},
        )
        self.assertEqual(list(g.tags.all()), [])

    def test_bucket_bulk_tags(self):
        a = f.tag(self.alice, "A")
        bk = f.bucket(self.alice, "1")
        self.post(
            "bucket_bulk_tags",
            {"action": "add", "item_ids": [bk.pk], "tag_ids": [a.pk]},
        )
        self.assertEqual(list(bk.tags.all()), [a])

    def test_expense_tags_are_per_user(self):
        a, b = f.tag(self.alice, "A"), f.tag(self.alice, "B")
        shared = f.expense(self.bob, "1", shared_with=[self.alice])
        UserExpenseTag.objects.create(
            user=self.bob, expense=shared, tag=f.tag(self.bob, "Bobs")
        )

        def mine():
            return set(
                UserExpenseTag.objects.filter(user=self.alice).values_list(
                    "tag_id", flat=True
                )
            )

        self.post(
            "expense_bulk_tags",
            {"action": "add", "item_ids": [shared.pk], "tag_ids": [a.pk, b.pk]},
        )
        self.post(
            "expense_bulk_tags",
            {"action": "add", "item_ids": [shared.pk], "tag_ids": [a.pk]},
        )
        self.assertEqual(mine(), {a.pk, b.pk})
        self.post(
            "expense_bulk_tags",
            {"action": "remove", "item_ids": [shared.pk], "tag_ids": [a.pk]},
        )
        self.assertEqual(mine(), {b.pk})
        self.post(
            "expense_bulk_tags",
            {"action": "set", "item_ids": [shared.pk], "tag_ids": [a.pk]},
        )
        self.assertEqual(mine(), {a.pk})
        self.assertEqual(UserExpenseTag.objects.filter(user=self.bob).count(), 1)

    def test_invalid_json_and_action(self):
        self.assertEqual(self.post("income_bulk_tags", "not json").status_code, 400)
        self.assertEqual(
            self.post("income_bulk_tags", {"action": "nuke"}).status_code, 400
        )

    def test_get_not_allowed(self):
        self.assertEqual(
            self.client.get(reverse("finances:income_bulk_tags")).status_code, 405
        )


class BoundaryTests(LoggedInTestCase):
    """Untrusted input must be rejected or ignored, never crash with a 500."""

    def bulk(self, payload):
        return self.client.post(
            reverse("finances:income_bulk_tags"),
            json.dumps(payload),
            content_type="application/json",
        )

    def test_dashboard_ignores_non_numeric_tag(self):
        f.expense(self.alice, "100")
        response = self.client.get(reverse("finances:dashboard"), {"tag": "abc"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["tag_filter"])
        self.assertEqual(len(response.context["expenses_data"]), 1)

    def test_dashboard_ignores_other_users_tag(self):
        f.expense(self.alice, "100")
        bob_tag = f.tag(self.bob, "Bob")
        response = self.client.get(reverse("finances:dashboard"), {"tag": bob_tag.id})
        self.assertIsNone(response.context["tag_filter"])
        self.assertEqual(len(response.context["expenses_data"]), 1)

    def test_bulk_tags_rejects_malformed_payloads(self):
        inc = f.income(self.alice, "1")
        for payload in [
            ["not", "an", "object"],
            {"action": "add", "item_ids": "abc", "tag_ids": []},
            {"action": "add", "item_ids": ["x"], "tag_ids": []},
            {"action": "add", "item_ids": [inc.pk], "tag_ids": [None]},
            {"action": "add", "item_ids": [True], "tag_ids": []},
            {"action": ["add"], "item_ids": [], "tag_ids": []},
        ]:
            with self.subTest(payload=payload):
                response = self.bulk(payload)
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json()["ok"])

    def test_expense_payer_must_be_a_participant(self):
        carol = f.user("carol")
        response = self.client.post(
            reverse("finances:expense_add"),
            {
                "name": "Rent",
                "amount": "100",
                "frequency": "monthly",
                "shared_with": [self.bob.pk],
                "payer": carol.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("payer", response.context["form"].errors)
        self.assertFalse(Expense.objects.exists())

    def test_expense_payer_can_be_owner_or_shared_user(self):
        for payer in (self.alice, self.bob):
            self.client.post(
                reverse("finances:expense_add"),
                {
                    "name": f"Rent {payer}",
                    "amount": "100",
                    "frequency": "monthly",
                    "shared_with": [self.bob.pk],
                    "payer": payer.pk,
                },
            )
        self.assertEqual(
            set(Expense.objects.values_list("payer", flat=True)),
            {self.alice.pk, self.bob.pk},
        )


class ParticipantEditTests(LoggedInTestCase):
    def test_participant_edit_keeps_them_shared_and_never_offers_owner(self):
        carol = f.user("carol")
        exp = f.expense(self.bob, "300", shared_with=[self.alice, carol])
        form = self.client.get(reverse("finances:expense_edit", args=[exp.pk])).context[
            "form"
        ]
        choices = set(form.fields["shared_with"].queryset)
        self.assertEqual(choices, {self.alice, carol})

        # Submit what the browser would send back unchanged.
        self.client.post(
            reverse("finances:expense_edit", args=[exp.pk]),
            {
                "name": "Rent",
                "amount": "300",
                "frequency": "monthly",
                "shared_with": [self.alice.pk, carol.pk],
            },
        )
        exp.refresh_from_db()
        self.assertEqual(set(exp.shared_with.all()), {self.alice, carol})
        self.assertEqual(exp.share_for(self.alice), Decimal("100.00"))


class LocalDateTests(LoggedInTestCase):
    """Month logic must use the configured local date, not the UTC date."""

    @override_settings(TIME_ZONE="Europe/Zurich")
    def test_due_month_follows_local_time_zone(self):
        f.annual_expense(self.alice, "1200", 3, name="Tax")
        # 23:30 UTC on 28 Feb is already 00:30 on 1 March in Zurich.
        late_feb_utc = datetime(2025, 2, 28, 23, 30, tzinfo=UTC)
        with patch("django.utils.timezone.now", return_value=late_feb_utc):
            ctx = self.client.get(reverse("finances:dashboard")).context
        self.assertEqual([e.name for e in ctx["annual_due_expenses"]], ["Tax"])
        self.assertEqual(ctx["snapshot"]["annual_withdrawals"], Decimal("1200.00"))


class QueryCountTests(LoggedInTestCase):
    """Page cost must not grow with the number of expenses (no N+1)."""

    def add_expenses(self, count, start):
        home = Tag.objects.get_or_create(owner=self.alice, name="Home")[0]
        for i in range(start, start + count):
            exp = f.expense(
                self.alice,
                "100",
                name=f"e{i}",
                shared_with=[self.bob],
                payer=self.alice,
                frequency="annual",
                target_month=date.today().month,
            )
            UserExpenseTag.objects.create(user=self.alice, expense=exp, tag=home)
        f.expense(self.bob, "50", name=f"bob{start}", shared_with=[self.alice])

    def queries_for(self, url):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(self.client.get(url).status_code, 200)
        return len(ctx)

    def test_dashboard_and_expense_list_queries_are_constant(self):
        self.add_expenses(2, 0)
        self.client.get("/")  # warm-up: first request creates SiteSettings
        before = {u: self.queries_for(u) for u in ("/", "/expenses/")}
        self.add_expenses(10, 100)
        after = {u: self.queries_for(u) for u in ("/", "/expenses/")}
        self.assertEqual(after, before)


class ThirteenthMonthDashboardTests(LoggedInTestCase):
    def test_charts_show_effective_amounts_matching_the_cards(self):
        travel = f.bucket(self.alice, "300", name="Travel")
        f.bucket(self.alice, "120", name="Car")
        rent = f.expense(self.alice, "500", name="Rent")
        f.expense(self.alice, "100", name="Phone")
        f.income(self.alice, "2400", months_per_year=13, thirteenth_month_bucket=travel)
        f.income(
            self.alice,
            "1200",
            name="Bonus job",
            months_per_year=13,
            thirteenth_month_expense=rent,
        )
        response = self.client.get(reverse("finances:dashboard"))
        ctx = response.context
        snap = ctx["snapshot"]
        self.assertContains(response, "13th month covers $100.00/mo")
        self.assertContains(response, "13th month covers $200.00/mo")
        self.assertEqual(ctx["expenses_total"], snap["monthly_expenses"])
        self.assertEqual(ctx["buckets_total"], snap["monthly_saving_buckets"])
        rows = {r["name"]: r for r in ctx["expenses_data"]}
        self.assertEqual(rows["Rent"]["value"], Decimal("400.00"))
        self.assertEqual(rows["Rent"]["covered"], Decimal("100.00"))
        self.assertNotIn("covered", rows["Phone"])
        buckets = {r["name"]: r for r in ctx["buckets_data"]}
        self.assertEqual(buckets["Travel"]["value"], Decimal("100.00"))
        self.assertEqual(buckets["Travel"]["covered"], Decimal("200.00"))
        self.assertEqual(ctx["combined_total"], snap["monthly_expenses"])
