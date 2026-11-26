from decimal import Decimal

from django.template import Context, Template
from django.test import TestCase

from finances.models import SiteSettings

from . import factories as f


def render(template, **context):
    return Template("{% load finances_extras %}" + template).render(Context(context))


class AmountTagTests(TestCase):
    def test_symbol_before_with_thousands_separator(self):
        cfg = SiteSettings(currency_symbol="$", currency_position="before")
        out = render("{% amount v %}", v=Decimal("1234.5"), site_settings=cfg)
        self.assertEqual(out, "$1,234.50")

    def test_symbol_after(self):
        cfg = SiteSettings(currency_symbol="Fr.", currency_position="after")
        self.assertEqual(
            render("{% amount v %}", v=Decimal(10), site_settings=cfg), "10.00Fr."
        )

    def test_non_numeric_value_renders_zero(self):
        cfg = SiteSettings(currency_symbol="€", currency_position="before")
        self.assertEqual(render("{% amount v %}", v=None, site_settings=cfg), "€0.00")

    def test_falls_back_to_stored_settings_without_context(self):
        SiteSettings(currency_symbol="£", currency_position="before").save()
        self.assertEqual(render("{% amount v %}", v=5), "£5.00")

    def test_symbol_is_escaped(self):
        cfg = SiteSettings(currency_symbol="<b>", currency_position="before")
        self.assertEqual(
            render("{% amount v %}", v=1, site_settings=cfg), "&lt;b&gt;1.00"
        )


class ExpenseFilterTests(TestCase):
    def test_share_tags_and_get_item_filters(self):
        alice, bob = f.user("alice"), f.user("bob")
        exp = f.annual_expense(alice, "1200", 6, shared_with=[bob])
        home = f.tag(bob, "Home")
        exp.user_tags.create(user=bob, tag=home)
        out = render(
            "{{ e|share_for:u }}|{{ e|annual_share_for:u }}|"
            "{% for t in e|tags_for:u %}{{ t.name }}{% endfor %}|{{ d|get_item:k }}",
            e=exp,
            u=bob,
            d={3: "three"},
            k=3,
        )
        self.assertEqual(out, "50.00|600.00|Home|three")
