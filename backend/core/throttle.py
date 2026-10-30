"""Failed-sign-in throttling (D40 (5)). Counts live in the database so every worker sees the same numbers.

Only a hash of the email address is stored. The web role reaches the table through SECURITY DEFINER
functions, because nobody is identified yet when these checks run.
"""

import hashlib
from datetime import timedelta

from django.conf import settings
from django.db import connection


def _key(email):
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def _call(sql, params):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
        return row[0] if row else None


def is_locked(email):
    window = timedelta(seconds=settings.LOGIN_FAILURE_WINDOW_SECONDS)
    failures = _call("SELECT login_failures_in_window(%s, %s)", [_key(email), window])
    return failures >= settings.LOGIN_MAX_FAILURES


def record_failure(email):
    _call("SELECT record_login_failure(%s)", [_key(email)])


def clear(email):
    _call("SELECT clear_login_failures(%s)", [_key(email)])
