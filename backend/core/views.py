from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render


def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return JsonResponse({"status": "ok", "database": "ok"})


def home(request):
    if not request.user.is_authenticated:
        return HttpResponse(status=401)
    return render(request, "home.html")
