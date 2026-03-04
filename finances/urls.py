from django.urls import path

from . import views

app_name = "finances"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    # Income
    path("incomes/", views.IncomeListView.as_view(), name="income_list"),
    path("incomes/add/", views.IncomeCreateView.as_view(), name="income_add"),
    path(
        "incomes/<int:pk>/edit/", views.IncomeUpdateView.as_view(), name="income_edit"
    ),
    path(
        "incomes/<int:pk>/delete/",
        views.IncomeDeleteView.as_view(),
        name="income_delete",
    ),
    # Expense
    path("expenses/", views.ExpenseListView.as_view(), name="expense_list"),
    path("expenses/add/", views.ExpenseCreateView.as_view(), name="expense_add"),
    path(
        "expenses/<int:pk>/edit/",
        views.ExpenseUpdateView.as_view(),
        name="expense_edit",
    ),
    path(
        "expenses/<int:pk>/delete/",
        views.ExpenseDeleteView.as_view(),
        name="expense_delete",
    ),
    # SavingBucket
    path("buckets/", views.SavingBucketListView.as_view(), name="bucket_list"),
    path("buckets/add/", views.SavingBucketCreateView.as_view(), name="bucket_add"),
    path(
        "buckets/<int:pk>/edit/",
        views.SavingBucketUpdateView.as_view(),
        name="bucket_edit",
    ),
    path(
        "buckets/<int:pk>/delete/",
        views.SavingBucketDeleteView.as_view(),
        name="bucket_delete",
    ),
    # SavingsGoal
    path("goals/", views.SavingsGoalListView.as_view(), name="goal_list"),
    path("goals/add/", views.SavingsGoalCreateView.as_view(), name="goal_add"),
    path(
        "goals/<int:pk>/edit/", views.SavingsGoalUpdateView.as_view(), name="goal_edit"
    ),
    path(
        "goals/<int:pk>/delete/",
        views.SavingsGoalDeleteView.as_view(),
        name="goal_delete",
    ),
    # Bulk tag actions
    path('incomes/bulk-tags/', views.IncomeBulkTagsView.as_view(), name='income_bulk_tags'),
    path('expenses/bulk-tags/', views.ExpenseBulkTagsView.as_view(), name='expense_bulk_tags'),
    path('buckets/bulk-tags/', views.SavingBucketBulkTagsView.as_view(), name='bucket_bulk_tags'),
    path('goals/bulk-tags/', views.SavingsGoalBulkTagsView.as_view(), name='goal_bulk_tags'),
    # Tag
    path("tags/", views.TagListView.as_view(), name="tag_list"),
    path("tags/add/", views.TagCreateView.as_view(), name="tag_add"),
    path("tags/<int:pk>/edit/", views.TagUpdateView.as_view(), name="tag_edit"),
    path("tags/<int:pk>/delete/", views.TagDeleteView.as_view(), name="tag_delete"),
]
