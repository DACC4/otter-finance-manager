from decimal import Decimal
from typing import Iterable

from django.conf import settings
from django.db import models
from django.utils import timezone


class Frequency(models.TextChoices):
    MONTHLY = "monthly", "Monthly"
    ANNUAL = "annual", "Annual"


class Tag(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tags",
    )
    name = models.CharField(max_length=50)
    color = models.CharField(
        max_length=7,
        default="#3b82f6",
        help_text="Hex color code (e.g., #3b82f6)",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("owner", "name")]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.name} ({self.owner})"


class Income(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="incomes",
    )
    name = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    frequency = models.CharField(
        max_length=10, choices=Frequency.choices, default=Frequency.MONTHLY
    )
    months_per_year = models.PositiveSmallIntegerField(
        choices=[(12, "12 months"), (13, "13 months")],
        default=12,
        help_text="Choose 13 if your salary includes a 13th-month payment.",
    )
    thirteenth_month_bucket = models.ForeignKey(
        "SavingBucket",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Saving bucket to allocate the 13th month payment to.",
    )
    thirteenth_month_expense = models.ForeignKey(
        "Expense",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Expense to allocate the 13th month payment to.",
    )
    tags = models.ManyToManyField(Tag, related_name="incomes", blank=True)
    start_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.name} ({self.owner})"

    @property
    def monthly_amount(self) -> Decimal:
        if self.frequency == Frequency.MONTHLY:
            return self.amount
        return (self.amount / Decimal(self.months_per_year)).quantize(Decimal("0.01"))

    @property
    def thirteenth_month_amount(self) -> Decimal:
        if self.months_per_year != 13:
            return Decimal("0")
        return self.monthly_amount


class Expense(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="expenses",
    )
    name = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    frequency = models.CharField(
        max_length=10, choices=Frequency.choices, default=Frequency.MONTHLY
    )
    target_month = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        help_text="Month (1-12) when this annual expense is paid",
    )
    shared_with = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="shared_expenses",
        blank=True,
    )
    payer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fronted_expenses",
        help_text="Who pays this bill upfront. Leave blank if everyone pays their own share directly.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.name} ({self.owner})"

    @property
    def monthly_amount(self) -> Decimal:
        if self.frequency == Frequency.MONTHLY:
            return self.amount
        return (self.amount / Decimal("12")).quantize(Decimal("0.01"))

    @property
    def participant_count(self) -> int:
        # owner counts as a participant even if shared_with is empty
        return 1 + self.shared_with.count()

    def participants(self) -> Iterable[settings.AUTH_USER_MODEL]:
        yield self.owner
        yield from self.shared_with.all()

    def share_for(self, user) -> Decimal:
        if user == self.owner or self.shared_with.filter(pk=user.pk).exists():
            count = max(self.participant_count, 1)
            return (self.monthly_amount / Decimal(count)).quantize(Decimal("0.01"))
        return Decimal("0")

    def annual_share_for(self, user) -> Decimal:
        """User's share of the full annual amount (used when the bill is due)."""
        if self.frequency != Frequency.ANNUAL:
            return Decimal("0")
        if user != self.owner and not self.shared_with.filter(pk=user.pk).exists():
            return Decimal("0")
        count = max(self.participant_count, 1)
        return (self.amount / Decimal(count)).quantize(Decimal("0.01"))

    def monthly_annual_saving(self, user) -> Decimal:
        """Even monthly saving needed to cover this annual bill."""
        share = self.annual_share_for(user)
        if share == 0:
            return Decimal("0")
        return (share / Decimal("12")).quantize(Decimal("0.01"))

    def _target_month_value(self) -> int:
        """Treat unset target_month as December (12) for predictable cycles."""
        return self.target_month or 12

    def months_into_cycle(self, as_of=None) -> int:
        """
        Number of months since the last due month (1-12). On the due month this
        returns 12, meaning you should have the full amount saved.
        """
        as_of = as_of or timezone.now().date()
        target = self._target_month_value()
        delta = (as_of.month - target) % 12
        return 12 if delta == 0 else delta

    def is_due_in_month(self, as_of=None) -> bool:
        as_of = as_of or timezone.now().date()
        return as_of.month == self._target_month_value()

    def expected_annual_balance(self, user, as_of=None) -> Decimal:
        """
        How much should be set aside right now for this annual expense (per user),
        assuming even saving across the year and reset after payment.
        """
        if self.frequency != Frequency.ANNUAL:
            return Decimal("0")
        monthly_share = self.share_for(user)
        months_saved = self.months_into_cycle(as_of=as_of)
        return (monthly_share * Decimal(months_saved)).quantize(Decimal("0.01"))


class UserExpenseTag(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="expense_tags",
    )
    expense = models.ForeignKey(
        Expense,
        on_delete=models.CASCADE,
        related_name="user_tags",
    )
    tag = models.ForeignKey(
        Tag,
        on_delete=models.CASCADE,
        related_name="expense_links",
    )

    class Meta:
        unique_together = [("user", "expense", "tag")]


class SavingBucket(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saving_buckets",
    )
    name = models.CharField(max_length=120)
    monthly_contribution = models.DecimalField(max_digits=12, decimal_places=2)
    tags = models.ManyToManyField(Tag, related_name="saving_buckets", blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.name} ({self.owner})"


class SavingsGoal(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="savings_goals",
    )
    name = models.CharField(max_length=120)
    target_amount = models.DecimalField(max_digits=12, decimal_places=2)
    target_date = models.DateField()
    current_balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    tags = models.ManyToManyField(Tag, related_name="savings_goals", blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["target_date", "name"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.name} ({self.owner})"

    def months_remaining(self, as_of=None) -> int:
        as_of = as_of or timezone.now().date()
        if self.target_date <= as_of:
            return 1
        months = (self.target_date.year - as_of.year) * 12 + (
            self.target_date.month - as_of.month
        )
        return max(months, 1)

    def required_monthly_saving(self, as_of=None) -> Decimal:
        as_of = as_of or timezone.now().date()
        remaining = self.target_amount - self.current_balance
        if remaining <= 0:
            return Decimal("0")
        months = self.months_remaining(as_of=as_of)
        return (remaining / Decimal(months)).quantize(Decimal("0.01"))


class SiteSettings(models.Model):
    currency_symbol = models.CharField(
        max_length=8, default="$",
        help_text='Symbol shown next to amounts, e.g. "$", "€", "£", "Fr."',
    )
    currency_position = models.CharField(
        max_length=6,
        choices=[("before", "Before amount  →  $100.00"), ("after", "After amount  →  100.00$")],
        default="before",
    )
    date_format = models.CharField(
        max_length=20,
        choices=[
            ("m/d/Y", "MM/DD/YYYY — 03/02/2026"),
            ("d/m/Y", "DD/MM/YYYY — 02/03/2026"),
            ("Y-m-d", "YYYY-MM-DD — 2026-03-02"),
            ("d.m.Y", "DD.MM.YYYY — 02.03.2026"),
            ("j F Y", "D Month YYYY — 2 March 2026"),
            ("j M Y", "D Mon YYYY — 2 Mar 2026"),
        ],
        default="m/d/Y",
    )

    class Meta:
        verbose_name = "Site settings"
        verbose_name_plural = "Site settings"

    def __str__(self):
        return "Site settings"

    def save(self, *args, **kwargs):
        self.pk = 1          # enforce singleton
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
