"""A test-only URL configuration: one view that reports what the database sees during a request."""

from django.db import connection
from django.http import JsonResponse
from django.urls import include, path

from core.models import Company


def probe(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user")
        role = cursor.fetchone()[0]
        cursor.execute("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
        bypasses_rls = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM pg_tables WHERE tableowner = current_user")
        tables_owned = cursor.fetchone()[0]
    return JsonResponse(
        {
            "role": role,
            "bypasses_rls": bypasses_rls,
            "tables_owned": tables_owned,
            "companies": sorted(Company.objects.values_list("name", flat=True)),
        }
    )


def boom(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 / 0")


urlpatterns = [path("probe/", probe), path("boom/", boom), path("", include("config.urls"))]
