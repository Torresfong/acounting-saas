"""Single-use, expiring links for password setup and reset (D40 (5)).

The token is random and only its SHA-256 hash is stored. Everything that runs before anyone is signed in
goes through SECURITY DEFINER functions (D40 (2)).
"""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import DatabaseError, connection, transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from . import ports


class InvalidLink(Exception):
    """The link is unknown, expired or already used. The three cases are deliberately not told apart."""


def new_token():
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def _scalar(sql, params):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()[0]


def link_is_valid(raw, purpose):
    return _scalar("SELECT token_is_valid(%s, %s)", [hash_token(raw), purpose])


def request_password_reset(email, build_url):
    """Email a reset link if the address has an account; do nothing otherwise. The caller answers the same either way."""
    raw, hashed = new_token()
    expires = timezone.now() + timedelta(hours=settings.RESET_LINK_HOURS)
    if not _scalar("SELECT create_password_reset(%s, %s, %s)", [hashed, email, expires]):
        return
    ports.get().email.send(
        email,
        _("Reset your password"),
        _("Use this link to choose a new password. It works once and expires in %(hours)s hour(s):\n\n%(url)s\n")
        % {"hours": settings.RESET_LINK_HOURS, "url": build_url(raw)},
    )


def complete_password_reset(raw, password):
    try:
        # A savepoint keeps the refusal from aborting the request's transaction.
        with transaction.atomic():
            return _scalar("SELECT complete_password_reset(%s, %s)", [hash_token(raw), make_password(password)])
    except DatabaseError as error:
        raise InvalidLink from error
