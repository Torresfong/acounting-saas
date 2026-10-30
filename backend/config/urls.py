from django.urls import path

from core.views import health, home, password_reset_confirm, password_reset_request, sign_in, sign_out

urlpatterns = [
    path("", home),
    path("health/", health),
    path("login/", sign_in),
    path("logout/", sign_out),
    path("password-reset/", password_reset_request),
    path("reset/<str:token>/", password_reset_confirm),
]
