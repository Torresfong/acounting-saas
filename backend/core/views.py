from django.contrib.auth import logout, password_validation
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import permissions, throttle, tokens
from .auth import EmailBackend
from .models import AuthToken, CompanyAccess
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


def companies(request):
    """The companies the signed-in user can reach. Row-level security does the filtering; the role is shown for context."""
    if not request.user.is_authenticated:
        return HttpResponse(status=401)
    accesses = CompanyAccess.objects.filter(user=request.user).select_related("company").order_by("company__name")
    return render(request, "companies.html", {"accesses": accesses})


def company(request, pk):
    if not request.user.is_authenticated:
        return HttpResponse(status=401)
    # A company the user cannot reach is not found, so its existence is not revealed.
    access = get_object_or_404(CompanyAccess.objects.select_related("company"), user=request.user, company_id=pk)
    permissions.require(request.user, "view_company", access.company)
    return _company_page(request, access)


def _company_page(request, access, **extra):
    context = {"company": access.company, "access": access, **extra}
    if request.GET.get("invited"):
        context["message"] = _("Invitation sent.")
    return render(request, "company.html", context)


@require_POST
def invite_staff(request, pk):
    if not request.user.is_authenticated:
        return HttpResponse(status=401)
    access = get_object_or_404(CompanyAccess.objects.select_related("company"), user=request.user, company_id=pk)
    permissions.require(request.user, "invite_staff", access.company)

    email = request.POST.get("email", "").strip()
    try:
        validate_email(email)
        tokens.invite_staff(access.company, email, lambda raw: request.build_absolute_uri(f"/accept/{raw}/"))
    except (ValidationError, IntegrityError):
        # One message for both, so the owner cannot probe which addresses already have an account.
        return _company_page(request, access, error=_("That email address cannot be invited."))
    return redirect(f"/companies/{pk}/?invited=1")


def accept_invitation(request, token):
    return _choose_password(
        request, token, AuthToken.INVITE, _("Choose your password"), tokens.accept_invitation
    )
