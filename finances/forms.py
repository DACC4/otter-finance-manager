import calendar

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from .models import Expense, Income, SavingBucket, SavingsGoal, Tag

User = get_user_model()


class UserTagsMixin:
    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if user and "tags" in self.fields:
            self.fields["tags"].queryset = Tag.objects.filter(owner=user)


class IncomeForm(UserTagsMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        user = kwargs.get("user")
        super().__init__(*args, **kwargs)
        if user:
            self.fields["thirteenth_month_bucket"].queryset = (
                SavingBucket.objects.filter(owner=user)
            )
            self.fields["thirteenth_month_expense"].queryset = (
                Expense.objects.filter(
                    Q(owner=user) | Q(shared_with=user)
                ).distinct()
            )

    def clean(self):
        cleaned = super().clean()
        if (
            cleaned.get("months_per_year") == 13
            and cleaned.get("thirteenth_month_bucket")
            and cleaned.get("thirteenth_month_expense")
        ):
            raise forms.ValidationError(
                "Assign the 13th month to either a saving bucket or an expense — not both."
            )
        return cleaned

    class Meta:
        model = Income
        fields = [
            "name", "amount", "frequency", "months_per_year",
            "thirteenth_month_bucket", "thirteenth_month_expense",
            "tags", "start_date",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "tags": forms.SelectMultiple(attrs={"size": 3}),
        }


class ExpenseForm(UserTagsMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["target_month"].help_text = "Only relevant for annual expenses."
        self.fields["payer"].empty_label = "No single payer (everyone pays directly)"
        if self.instance.pk:
            participant_pks = [self.instance.owner_id] + list(
                self.instance.shared_with.values_list("pk", flat=True)
            )
            self.fields["payer"].queryset = User.objects.filter(pk__in=participant_pks)
        else:
            self.fields["payer"].queryset = User.objects.all()

    class Meta:
        model = Expense
        fields = ["name", "amount", "frequency", "target_month", "tags", "shared_with", "payer"]
        widgets = {
            "tags": forms.SelectMultiple(attrs={"size": 3}),
            "shared_with": forms.SelectMultiple(attrs={"size": 3}),
            "target_month": forms.Select(
                choices=[("", "---------")]
                + [(i, calendar.month_name[i]) for i in range(1, 13)],
            ),
        }


class SavingBucketForm(UserTagsMixin, forms.ModelForm):
    class Meta:
        model = SavingBucket
        fields = ["name", "monthly_contribution", "tags", "description"]
        widgets = {
            "tags": forms.SelectMultiple(attrs={"size": 3}),
            "description": forms.Textarea(attrs={"rows": 2}),
        }


class SavingsGoalForm(UserTagsMixin, forms.ModelForm):
    class Meta:
        model = SavingsGoal
        fields = [
            "name",
            "target_amount",
            "target_date",
            "current_balance",
            "tags",
            "notes",
        ]
        widgets = {
            "target_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "tags": forms.SelectMultiple(attrs={"size": 3}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class TagForm(UserTagsMixin, forms.ModelForm):
    class Meta:
        model = Tag
        fields = ["name", "color"]
        widgets = {
            "color": forms.TextInput(attrs={"type": "color"}),
        }
