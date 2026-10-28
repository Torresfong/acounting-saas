from django.urls import path

from core.views import health, home

urlpatterns = [
    path("", home),
    path("health/", health),
]
