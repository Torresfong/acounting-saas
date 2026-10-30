from django.urls import path

from core.views import accept_invitation, companies, company, health, invite_staff, home, password_reset_confirm, password_reset_request, sign_in, sign_out

urlpatterns = [
    path("", home),
    path("health/", health),
    path("login/", sign_in),
    path("logout/", sign_out),
    path("companies/", companies),
    path("companies/<int:pk>/", company),
    path("companies/<int:pk>/invite/", invite_staff),
    path("accept/<str:token>/", accept_invitation),
    path("password-reset/", password_reset_request),
    path("reset/<str:token>/", password_reset_confirm),
]
