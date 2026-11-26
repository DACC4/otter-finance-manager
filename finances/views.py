from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponseForbidden, JsonResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    ListView,
    TemplateView,
    UpdateView,
)

from .forms import ExpenseForm, IncomeForm, SavingBucketForm, SavingsGoalForm, TagForm
from .models import (
    Expense,
    Frequency,
    Income,
    SavingBucket,
    SavingsGoal,
    Tag,
    UserExpenseTag,
)
from .parsing import InvalidPayload, parse_bulk_tags_payload, parse_owned_tag_id
from .services import (
    calculate_debts,
    calculate_financial_snapshot,
    effective_bucket_contribution,
    expense_split_totals,
    goal_progress,
    max_value,
    sort_rows,
    tag_expense_rows,
    thirteenth_month_bucket_reductions,
    total_value,
    value_rows,
)


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "finances/dashboard.html"

    def _querysets(self, user, tag_id):
        """The user's items, narrowed to one of their tags when a filter is set."""
        incomes = Income.objects.filter(owner=user)
        expenses = Expense.objects.visible_to(user)
        buckets = SavingBucket.objects.filter(owner=user)
        goals = SavingsGoal.objects.filter(owner=user)
        if tag_id is not None:
            incomes = incomes.filter(tags__id=tag_id)
            expenses = expenses.filter(user_tags__user=user, user_tags__tag_id=tag_id)
            buckets = buckets.filter(tags__id=tag_id)
            goals = goals.filter(tags__id=tag_id)
        return incomes, expenses, buckets, goals

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        as_of = timezone.now().date()
        sort_option = (self.request.GET.get("sort") or "price_desc").lower()
        tags = Tag.objects.filter(owner=user)
        tag_id = parse_owned_tag_id(
            self.request.GET.get("tag"), tags.values_list("id", flat=True)
        )
        incomes, expenses, buckets, goals = self._querysets(user, tag_id)

        charts = {
            "incomes": value_rows(incomes, lambda i: i.monthly_amount),
            "expenses": value_rows(expenses, lambda e: e.share_for(user)),
            "buckets": value_rows(buckets, lambda b: b.monthly_contribution),
            "goals": value_rows(goals, lambda g: g.required_monthly_saving(as_of)),
            "tag_expense": tag_expense_rows(tags, expenses, user),
        }
        for name, rows in charts.items():
            rows = sort_rows(rows, sort_option)
            context[f"{name}_data"] = rows
            context[f"{name}_max"] = max_value(rows)
            context[f"{name}_total"] = total_value(rows)

        snapshot = calculate_financial_snapshot(user)
        context.update(expense_split_totals(expenses, user))
        context.update(
            {
                "snapshot": snapshot,
                "fun_negative": snapshot["fun_money"] < 0,
                "savings_goals": [goal_progress(g, as_of) for g in goals],
                "annual_due_expenses": [
                    e
                    for e in expenses
                    if e.frequency == Frequency.ANNUAL and e.is_due_in_month(as_of)
                ],
                "thirteenth_month_incomes": [
                    i for i in incomes if i.months_per_year == 13
                ],
                "tag_filter": tag_id,
                "tags": tags,
            }
        )
        return context


class OwnerCheckMixin(UserPassesTestMixin):
    """Ensure the user is the owner of the object."""

    def test_func(self):
        obj = self.get_object()
        return obj.owner == self.request.user

    def handle_no_permission(self):
        return HttpResponseForbidden("You don't have permission to edit this.")


class UserFormKwargsMixin:
    """Forms scope their choices (tags, buckets, users) to the current user."""

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user}


class OwnerCreateMixin(LoginRequiredMixin, UserFormKwargsMixin):
    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


class OwnerUpdateMixin(LoginRequiredMixin, OwnerCheckMixin, UserFormKwargsMixin):
    pass


class OwnedListMixin(LoginRequiredMixin):
    """List only the current user's own objects."""

    def get_queryset(self):
        return self.model.objects.filter(owner=self.request.user)


class UserTagsContextMixin:
    """Expose the user's tags to the bulk-tagging toolbar."""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["user_tags"] = list(
            Tag.objects.filter(owner=self.request.user).values("id", "name", "color")
        )
        return ctx


class IncomeListView(OwnedListMixin, UserTagsContextMixin, ListView):
    model = Income
    template_name = "finances/income_list.html"
    context_object_name = "incomes"


class IncomeCreateView(OwnerCreateMixin, CreateView):
    model = Income
    form_class = IncomeForm
    template_name = "finances/form.html"
    success_url = reverse_lazy("finances:income_list")
    extra_context = {"title": "Add income"}


class IncomeUpdateView(OwnerUpdateMixin, UpdateView):
    model = Income
    form_class = IncomeForm
    template_name = "finances/form.html"
    success_url = reverse_lazy("finances:income_list")
    extra_context = {"title": "Edit income"}


class IncomeDeleteView(LoginRequiredMixin, OwnerCheckMixin, DeleteView):
    model = Income
    template_name = "finances/confirm_delete.html"
    success_url = reverse_lazy("finances:income_list")


class ExpenseListView(LoginRequiredMixin, UserTagsContextMixin, ListView):
    model = Expense
    template_name = "finances/expense_list.html"
    context_object_name = "expenses"

    def get_queryset(self):
        return Expense.objects.visible_to(self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["debts"] = calculate_debts(self.request.user)
        return ctx


class ExpenseCreateView(OwnerCreateMixin, CreateView):
    model = Expense
    form_class = ExpenseForm
    template_name = "finances/form.html"
    success_url = reverse_lazy("finances:expense_list")
    extra_context = {"title": "Add expense"}


class ExpenseUpdateView(OwnerUpdateMixin, UpdateView):
    model = Expense
    form_class = ExpenseForm
    template_name = "finances/form.html"
    success_url = reverse_lazy("finances:expense_list")
    extra_context = {"title": "Edit expense"}

    def test_func(self):
        # Allow the owner or any participant (shared_with) to edit the expense
        return self.get_object().has_participant(self.request.user)


class ExpenseDeleteView(LoginRequiredMixin, OwnerCheckMixin, DeleteView):
    model = Expense
    template_name = "finances/confirm_delete.html"
    success_url = reverse_lazy("finances:expense_list")


class SavingBucketListView(OwnedListMixin, UserTagsContextMixin, ListView):
    model = SavingBucket
    template_name = "finances/bucket_list.html"
    context_object_name = "buckets"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        reductions = thirteenth_month_bucket_reductions(
            Income.objects.filter(owner=self.request.user)
        )
        ctx["bucket_reductions"] = reductions
        ctx["bucket_effective"] = {
            bucket.pk: effective_bucket_contribution(bucket, reductions)
            for bucket in ctx["buckets"]
            if bucket.pk in reductions
        }
        return ctx


class SavingBucketCreateView(OwnerCreateMixin, CreateView):
    model = SavingBucket
    form_class = SavingBucketForm
    template_name = "finances/form.html"
    success_url = reverse_lazy("finances:bucket_list")
    extra_context = {"title": "Add saving bucket"}


class SavingBucketUpdateView(OwnerUpdateMixin, UpdateView):
    model = SavingBucket
    form_class = SavingBucketForm
    template_name = "finances/form.html"
    success_url = reverse_lazy("finances:bucket_list")
    extra_context = {"title": "Edit saving bucket"}


class SavingBucketDeleteView(LoginRequiredMixin, OwnerCheckMixin, DeleteView):
    model = SavingBucket
    template_name = "finances/confirm_delete.html"
    success_url = reverse_lazy("finances:bucket_list")


class SavingsGoalListView(OwnedListMixin, UserTagsContextMixin, ListView):
    model = SavingsGoal
    template_name = "finances/goal_list.html"
    context_object_name = "goals"


class SavingsGoalCreateView(OwnerCreateMixin, CreateView):
    model = SavingsGoal
    form_class = SavingsGoalForm
    template_name = "finances/form.html"
    success_url = reverse_lazy("finances:goal_list")
    extra_context = {"title": "Add savings goal"}


class SavingsGoalUpdateView(OwnerUpdateMixin, UpdateView):
    model = SavingsGoal
    form_class = SavingsGoalForm
    template_name = "finances/form.html"
    success_url = reverse_lazy("finances:goal_list")
    extra_context = {"title": "Edit savings goal"}


class SavingsGoalDeleteView(LoginRequiredMixin, OwnerCheckMixin, DeleteView):
    model = SavingsGoal
    template_name = "finances/confirm_delete.html"
    success_url = reverse_lazy("finances:goal_list")


class TagListView(OwnedListMixin, ListView):
    model = Tag
    template_name = "finances/tag_list.html"
    context_object_name = "tags"


class TagCreateView(OwnerCreateMixin, CreateView):
    model = Tag
    form_class = TagForm
    template_name = "finances/form.html"
    success_url = reverse_lazy("finances:tag_list")
    extra_context = {"title": "Add tag"}


class TagUpdateView(LoginRequiredMixin, OwnerCheckMixin, UpdateView):
    model = Tag
    form_class = TagForm
    template_name = "finances/form.html"
    success_url = reverse_lazy("finances:tag_list")
    extra_context = {"title": "Edit tag"}


class TagDeleteView(LoginRequiredMixin, OwnerCheckMixin, DeleteView):
    model = Tag
    template_name = "finances/confirm_delete.html"
    success_url = reverse_lazy("finances:tag_list")


class BulkTagsMixin(LoginRequiredMixin, View):
    http_method_names = ["post"]
    model = None

    def handle_no_permission(self):
        return JsonResponse(
            {"ok": False, "error": "Authentication required."}, status=403
        )

    def get_items_queryset(self, user, item_ids):
        return self.model.objects.filter(owner=user, pk__in=item_ids)

    def apply_tags(self, items, tags):
        for item in items:
            item.tags.add(*tags)

    def remove_tags(self, items, tags):
        for item in items:
            item.tags.remove(*tags)

    def set_tags(self, items, tags):
        for item in items:
            item.tags.set(tags)

    def post(self, request):
        try:
            action, item_ids, tag_ids = parse_bulk_tags_payload(request.body)
        except InvalidPayload as error:
            return JsonResponse({"ok": False, "error": str(error)}, status=400)
        items = list(self.get_items_queryset(request.user, item_ids))
        tags = list(Tag.objects.filter(owner=request.user, pk__in=tag_ids))
        handlers = {
            "add": self.apply_tags,
            "remove": self.remove_tags,
            "set": self.set_tags,
        }
        handlers[action](items, tags)
        return JsonResponse({"ok": True, "updated": len(items)})


class IncomeBulkTagsView(BulkTagsMixin):
    model = Income


class SavingBucketBulkTagsView(BulkTagsMixin):
    model = SavingBucket


class SavingsGoalBulkTagsView(BulkTagsMixin):
    model = SavingsGoal


class ExpenseBulkTagsView(BulkTagsMixin):
    model = Expense

    def get_items_queryset(self, user, item_ids):
        return Expense.objects.visible_to(user).filter(pk__in=item_ids)

    def apply_tags(self, items, tags):
        user = self.request.user
        for item in items:
            for tag in tags:
                UserExpenseTag.objects.get_or_create(user=user, expense=item, tag=tag)

    def remove_tags(self, items, tags):
        user = self.request.user
        UserExpenseTag.objects.filter(
            user=user, expense__in=items, tag__in=tags
        ).delete()

    def set_tags(self, items, tags):
        user = self.request.user
        UserExpenseTag.objects.filter(user=user, expense__in=items).delete()
        UserExpenseTag.objects.bulk_create(
            [
                UserExpenseTag(user=user, expense=item, tag=tag)
                for item in items
                for tag in tags
            ],
            ignore_conflicts=True,
        )
