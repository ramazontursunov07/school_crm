from django.urls import path

from . import views

urlpatterns = [
    path("billing/plans/", views.PlanListView.as_view(), name="plan-list"),
    path("billing/plans/<slug:code>/", views.PlanDetailView.as_view(), name="plan-detail"),
    path(
        "organizations/<int:org_id>/subscription/",
        views.SubscriptionView.as_view(),
        name="subscription-detail",
    ),
    path(
        "organizations/<int:org_id>/subscription/trial/",
        views.StartTrialView.as_view(),
        name="subscription-trial",
    ),
]
