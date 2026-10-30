from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.hashers import check_password, is_password_usable, make_password
from django.db import connection

# Verified against when the email is unknown, so an unknown address costs the same time as a wrong password.
_DUMMY_HASH = make_password("unknown-user-placeholder")


class EmailBackend(BaseBackend):
    """Sign in with an email address and a password.

    The lookup before anyone is identified goes through the `auth_lookup` function (D40 (2)), which
    returns only the id, the password hash and the active flag for an exact email match.
    """

    def authenticate(self, request, email=None, password=None, **kwargs):
        if not email or not password:
            return None
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, password, is_active FROM auth_lookup(%s)", [email])
            row = cursor.fetchone()
        if row is None or not is_password_usable(row[1]):
            # An unknown address and an account with no password yet cost as much as a wrong password.
            check_password(password, _DUMMY_HASH)
            return None
        user_id, encoded, is_active = row
        # No setter is passed on purpose: a hash upgrade would write the user table, which the web role cannot.
        if not check_password(password, encoded) or not is_active:
            return None
        return get_user_model()(pk=user_id, email=email.strip().lower(), password=encoded, is_active=is_active)

    def get_user(self, user_id):
        user = get_user_model().objects.filter(pk=user_id).first()
        return user if user is not None and user.is_active else None
