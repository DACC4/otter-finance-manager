from django.contrib import admin

from .models import Expense, Income, SavingBucket, SavingsGoal, SiteSettings, Tag


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "color", "created_at")
    list_filter = ("owner",)


@admin.register(Income)
class IncomeAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "amount", "frequency", "created_at")
    list_filter = ("frequency", "owner")
    filter_horizontal = ("tags",)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "amount", "frequency", "created_at")
    list_filter = ("frequency", "owner")
    filter_horizontal = ("shared_with",)


@admin.register(SavingBucket)
class SavingBucketAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "monthly_contribution", "created_at")
    list_filter = ("owner",)
    filter_horizontal = ("tags",)


@admin.register(SavingsGoal)
class SavingsGoalAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "owner",
        "target_amount",
        "target_date",
        "current_balance",
        "created_at",
    )
    list_filter = ("owner",)
    filter_horizontal = ("tags",)


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        from django.shortcuts import redirect
        from django.urls import reverse
        obj = SiteSettings.get()
        return redirect(reverse("admin:finances_sitesettings_change", args=[obj.pk]))
