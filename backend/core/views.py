from django.contrib.auth import logout, password_validation
from django.core.exceptions import ValidationError
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import throttle, tokens
from .auth import EmailBackend
from .models import AuthToken
from .signin import complete_sign_in


def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return JsonResponse({"status": "ok", "database": "ok"})


def home(request):
    if not request.user.is_authenticated:
        return HttpResponse(status=401)
    return render(request, "home.html")


def sign_in(request):
    if request.method != "POST":
        return render(request, "login.html")

    email = request.POST.get("email", "").strip()
    password = request.POST.get("password", "")
    context = {"email": email}

    if throttle.is_locked(email):
        context["error"] = _("Too many failed attempts. Try again in a few minutes.")
        return render(request, "login.html", context, status=429)

    user = EmailBackend().authenticate(request, email=email, password=password)
    if user is None:
        throttle.record_failure(email)
        context["error"] = _("The email address or password is not correct.")
        return render(request, "login.html", context)

    throttle.clear(email)
    complete_sign_in(request, user)
    return redirect("/")


@require_POST
def sign_out(request):
    logout(request)
    return redirect("/login/")


def _choose_password(request, token, purpose, heading, finish):
    """Choose a password through a single-use link. `finish(token, password)` consumes the link."""
    if not tokens.link_is_valid(token, purpose):
        return render(request, "link_invalid.html", status=410)
    if request.method != "POST":
        return render(request, "password_set.html", {"heading": heading})

    password = request.POST.get("password", "")
    errors = []
    if password != request.POST.get("confirm", ""):
        errors.append(_("The two passwords do not match."))
    else:
        try:
            password_validation.validate_password(password)
        except ValidationError as error:
            errors.extend(error.messages)
    if errors:
        return render(request, "password_set.html", {"heading": heading, "errors": errors})

    try:
        finish(token, password)
    except tokens.InvalidLink:
        return render(request, "link_invalid.html", status=410)
    return redirect("/login/")


def password_reset_request(request):
    if request.method != "POST":
        return render(request, "password_reset.html")
    email = request.POST.get("email", "").strip()
    if email:
        tokens.request_password_reset(email, lambda raw: request.build_absolute_uri(f"/reset/{raw}/"))
    return render(request, "password_reset.html", {"sent": True})


def password_reset_confirm(request, token):
    return _choose_password(
        request, token, AuthToken.RESET, _("Choose a new password"), tokens.complete_password_reset
    )
