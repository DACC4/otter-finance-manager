import json
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.http import HttpResponseForbidden, JsonResponse
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    ListView,
    UpdateView,
    TemplateView,
)

from django.utils import timezone

from .forms import ExpenseForm, IncomeForm, SavingBucketForm, SavingsGoalForm, TagForm
from .models import Expense, Frequency, Income, SavingBucket, SavingsGoal, Tag, UserExpenseTag
from .services import calculate_debts, calculate_financial_snapshot


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "finances/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        as_of = timezone.now().date()
        tag_id = self.request.GET.get("tag") or None
        tags = Tag.objects.filter(owner=user)

        incomes_qs = Income.objects.filter(owner=user)
        expenses_qs = Expense.objects.filter(
            Q(owner=user) | Q(shared_with=user)
        ).distinct()
        saving_buckets_qs = SavingBucket.objects.filter(owner=user)
        savings_goals_qs = SavingsGoal.objects.filter(owner=user)

        if tag_id:
            incomes_qs = incomes_qs.filter(tags__id=tag_id)
            expenses_qs = expenses_qs.filter(user_tags__user=user, user_tags__tag_id=tag_id)
            saving_buckets_qs = saving_buckets_qs.filter(tags__id=tag_id)
            savings_goals_qs = savings_goals_qs.filter(tags__id=tag_id)

        thirteenth_month_incomes = [
            inc for inc in incomes_qs if inc.months_per_year == 13
        ]

        annual_expenses = [
            exp for exp in expenses_qs if exp.frequency == Frequency.ANNUAL
        ]
        annual_due_expenses = [
            exp for exp in annual_expenses if exp.is_due_in_month(as_of)
        ]

        incomes_data = [
            {"name": inc.name, "value": inc.monthly_amount} for inc in incomes_qs
        ]
        expenses_data = [
            {"name": exp.name, "value": exp.share_for(user)} for exp in expenses_qs
        ]

        # Separate monthly vs annual expenses and compute shared/non-shared parts
        monthly_expense_rows = []
        annual_expense_rows = []
        monthly_shared_total = Decimal("0")
        monthly_non_shared_total = Decimal("0")
        annual_shared_total = Decimal("0")
        annual_non_shared_total = Decimal("0")

        for exp in expenses_qs:
            share = exp.share_for(user)
            is_shared = exp.participant_count > 1
            shared_amount = share if is_shared else Decimal("0")
            non_shared_amount = share if not is_shared else Decimal("0")
            row = {
                "id": exp.pk,
                "name": exp.name,
                "value": share,
                "shared_amount": shared_amount,
                "non_shared_amount": non_shared_amount,
                "is_shared": is_shared,
            }
            if exp.frequency == Frequency.ANNUAL:
                annual_expense_rows.append(row)
                annual_shared_total += shared_amount
                annual_non_shared_total += non_shared_amount
            else:
                monthly_expense_rows.append(row)
                monthly_shared_total += shared_amount
                monthly_non_shared_total += non_shared_amount

        monthly_total = monthly_shared_total + monthly_non_shared_total
        annual_total = annual_shared_total + annual_non_shared_total
        combined_total = monthly_total + annual_total
        buckets_data = [
            {"name": bucket.name, "value": bucket.monthly_contribution}
            for bucket in saving_buckets_qs
        ]
        goals_data = [
            {"name": goal.name, "value": goal.required_monthly_saving(as_of)}
            for goal in savings_goals_qs
        ]

        # Build a list of savings goals with progress information for the template
        savings_goals = []
        for goal in savings_goals_qs:
            try:
                percent = (goal.current_balance / goal.target_amount) * Decimal("100")
            except Exception:
                percent = Decimal("0")
            savings_goals.append(
                {
                    "id": goal.pk,
                    "name": goal.name,
                    "current": goal.current_balance,
                    "target": goal.target_amount,
                    "percent": percent.quantize(Decimal("0.01")),
                    "required_monthly": goal.required_monthly_saving(as_of),
                }
            )

        # Sorting option from querystring: 'price_desc' (default), 'price_asc', or 'none'
        sort_option = (self.request.GET.get("sort") or "price_desc").lower()
        if sort_option in ("price_desc", "price_asc"):
            reverse = sort_option == "price_desc"
            incomes_data = sorted(
                incomes_data, key=lambda d: d["value"], reverse=reverse
            )
            expenses_data = sorted(
                expenses_data, key=lambda d: d["value"], reverse=reverse
            )
            buckets_data = sorted(
                buckets_data, key=lambda d: d["value"], reverse=reverse
            )
            goals_data = sorted(goals_data, key=lambda d: d["value"], reverse=reverse)

        # Expenses by tag (sum of per-user share for expenses that have the tag)
        tag_expense_data = []
        for tag in tags:
            # sum share_for(user) for expenses that include this tag
            total = sum(
                (exp.share_for(user) for exp in expenses_qs.filter(user_tags__user=user, user_tags__tag_id=tag.id)),
                start=Decimal("0"),
            )
            if total > 0:
                tag_expense_data.append(
                    {"id": tag.id, "name": tag.name, "value": total, "color": tag.color}
                )

        # sort tag data according to sort option as well
        if sort_option in ("price_desc", "price_asc"):
            rev = sort_option == "price_desc"
            tag_expense_data = sorted(
                tag_expense_data, key=lambda d: d["value"], reverse=rev
            )

        def max_tag_value(data):
            return max([d["value"] for d in data], default=Decimal("1"))

        tag_expense_max = max_tag_value(tag_expense_data)
        tag_expense_total = sum(
            [d["value"] for d in tag_expense_data], start=Decimal("0")
        )

        def max_value(data):
            return max([d["value"] for d in data], default=1)

        def total_value(data):
            return sum([d["value"] for d in data], start=Decimal("0"))

        # Compute snapshot once so we can test whether fun_money is negative
        snapshot = calculate_financial_snapshot(user)
        fun_negative = snapshot.get("fun_money", 0) < 0

        context.update(
            {
                "snapshot": snapshot,
                "fun_negative": fun_negative,
                "savings_goals": savings_goals,
                "annual_due_expenses": annual_due_expenses,
                "tag_filter": tag_id,
                "tags": tags,
                "incomes_data": incomes_data,
                "expenses_data": expenses_data,
                "monthly_expense_rows": monthly_expense_rows,
                "annual_expense_rows": annual_expense_rows,
                "monthly_shared_total": monthly_shared_total,
                "monthly_non_shared_total": monthly_non_shared_total,
                "annual_shared_total": annual_shared_total,
                "annual_non_shared_total": annual_non_shared_total,
                "monthly_total": monthly_total,
                "annual_total": annual_total,
                "combined_total": combined_total,
                "buckets_data": buckets_data,
                "goals_data": goals_data,
                "incomes_max": max_value(incomes_data),
                "expenses_max": max_value(expenses_data),
                "buckets_max": max_value(buckets_data),
                "goals_max": max_value(goals_data),
                "incomes_total": total_value(incomes_data),
                "expenses_total": total_value(expenses_data),
                "buckets_total": total_value(buckets_data),
                "goals_total": total_value(goals_data),
                "tag_expense_data": tag_expense_data,
                "tag_expense_max": tag_expense_max,
                "tag_expense_total": tag_expense_total,
                "thirteenth_month_incomes": thirteenth_month_incomes,
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


class OwnerCreateMixin(LoginRequiredMixin):
    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class OwnerUpdateMixin(LoginRequiredMixin, OwnerCheckMixin):
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class IncomeListView(LoginRequiredMixin, ListView):
    model = Income
    template_name = "finances/income_list.html"
    context_object_name = "incomes"

    def get_queryset(self):
        return Income.objects.filter(owner=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['user_tags'] = list(Tag.objects.filter(owner=self.request.user).values('id', 'name', 'color'))
        return ctx


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


class ExpenseListView(LoginRequiredMixin, ListView):
    model = Expense
    template_name = "finances/expense_list.html"
    context_object_name = "expenses"

    def get_queryset(self):
        return Expense.objects.filter(
            Q(owner=self.request.user) | Q(shared_with=self.request.user)
        ).distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["debts"] = calculate_debts(self.request.user)
        ctx['user_tags'] = list(Tag.objects.filter(owner=self.request.user).values('id', 'name', 'color'))
        return ctx


class ExpenseCreateView(OwnerCreateMixin, CreateView):
    model = Expense
    form_class = ExpenseForm
    template_name = "finances/form.html"
    success_url = reverse_lazy("finances:expense_list")
    extra_context = {"title": "Add expense"}


class ExpenseUpdateView(LoginRequiredMixin, OwnerCheckMixin, UpdateView):
    model = Expense
    form_class = ExpenseForm
    template_name = "finances/form.html"
    success_url = reverse_lazy("finances:expense_list")
    extra_context = {"title": "Edit expense"}

    def test_func(self):
        # Allow the owner or any participant (shared_with) to edit the expense
        obj = self.get_object()
        return (
            obj.owner == self.request.user
            or obj.shared_with.filter(pk=self.request.user.pk).exists()
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs



class ExpenseDeleteView(LoginRequiredMixin, OwnerCheckMixin, DeleteView):
    model = Expense
    template_name = "finances/confirm_delete.html"
    success_url = reverse_lazy("finances:expense_list")


class SavingBucketListView(LoginRequiredMixin, ListView):
    model = SavingBucket
    template_name = "finances/bucket_list.html"
    context_object_name = "buckets"

    def get_queryset(self):
        return SavingBucket.objects.filter(owner=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['user_tags'] = list(Tag.objects.filter(owner=self.request.user).values('id', 'name', 'color'))
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


class SavingsGoalListView(LoginRequiredMixin, ListView):
    model = SavingsGoal
    template_name = "finances/goal_list.html"
    context_object_name = "goals"

    def get_queryset(self):
        return SavingsGoal.objects.filter(owner=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['user_tags'] = list(Tag.objects.filter(owner=self.request.user).values('id', 'name', 'color'))
        return ctx


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


class TagListView(LoginRequiredMixin, ListView):
    model = Tag
    template_name = "finances/tag_list.html"
    context_object_name = "tags"

    def get_queryset(self):
        return Tag.objects.filter(owner=self.request.user)


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
    http_method_names = ['post']
    model = None

    def handle_no_permission(self):
        return JsonResponse({'ok': False, 'error': 'Authentication required.'}, status=403)

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
            body = json.loads(request.body)
        except ValueError:
            return JsonResponse({'ok': False, 'error': 'Invalid JSON.'}, status=400)
        action = body.get('action')
        item_ids = body.get('item_ids', [])
        tag_ids = body.get('tag_ids', [])
        if action not in ('add', 'remove', 'set'):
            return JsonResponse({'ok': False, 'error': 'Invalid action.'}, status=400)
        items = list(self.get_items_queryset(request.user, item_ids))
        tags = list(Tag.objects.filter(owner=request.user, pk__in=tag_ids))
        if action == 'add':
            self.apply_tags(items, tags)
        elif action == 'remove':
            self.remove_tags(items, tags)
        elif action == 'set':
            self.set_tags(items, tags)
        return JsonResponse({'ok': True, 'updated': len(items)})


class IncomeBulkTagsView(BulkTagsMixin):
    model = Income


class SavingBucketBulkTagsView(BulkTagsMixin):
    model = SavingBucket


class SavingsGoalBulkTagsView(BulkTagsMixin):
    model = SavingsGoal


class ExpenseBulkTagsView(BulkTagsMixin):
    model = Expense

    def get_items_queryset(self, user, item_ids):
        return Expense.objects.filter(
            Q(owner=user) | Q(shared_with=user), pk__in=item_ids
        ).distinct()

    def apply_tags(self, items, tags):
        user = self.request.user
        for item in items:
            for tag in tags:
                UserExpenseTag.objects.get_or_create(user=user, expense=item, tag=tag)

    def remove_tags(self, items, tags):
        user = self.request.user
        UserExpenseTag.objects.filter(user=user, expense__in=items, tag__in=tags).delete()

    def set_tags(self, items, tags):
        user = self.request.user
        UserExpenseTag.objects.filter(user=user, expense__in=items).delete()
        UserExpenseTag.objects.bulk_create(
            [UserExpenseTag(user=user, expense=item, tag=tag) for item in items for tag in tags],
            ignore_conflicts=True,
        )
