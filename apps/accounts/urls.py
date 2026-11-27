from django.urls import path

from .views import (
    CsrfView,
    CurrentTokenView,
    DeviceDetailView,
    DeviceListView,
    DeviceRevokeAllView,
    LoginView,
    LogoutView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RegisterView,
    TokenLoginView,
    VerifyConfirmView,
    VerifyRequestView,
)

urlpatterns = [
    path("auth/csrf/", CsrfView.as_view(), name="auth-csrf"),
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("auth/verify/request/", VerifyRequestView.as_view(), name="auth-verify-request"),
    path("auth/verify/confirm/", VerifyConfirmView.as_view(), name="auth-verify-confirm"),
    path(
        "auth/password-reset/request/",
        PasswordResetRequestView.as_view(),
        name="auth-password-reset-request",
    ),
    path(
        "auth/password-reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="auth-password-reset-confirm",
    ),
    path("auth/token/", TokenLoginView.as_view(), name="auth-token-login"),
    path("auth/token/current/", CurrentTokenView.as_view(), name="auth-token-current"),
    path("auth/devices/", DeviceListView.as_view(), name="auth-device-list"),
    path("auth/devices/<int:pk>/", DeviceDetailView.as_view(), name="auth-device-detail"),
    path(
        "auth/devices/revoke-all/",
        DeviceRevokeAllView.as_view(),
        name="auth-device-revoke-all",
    ),
]
