"""Failed-sign-in throttling (D40 (5)). Counts live in the database so every worker sees the same numbers.

Only a hash of the email address is stored, worked out in the database. The web role reaches the table through SECURITY DEFINER
functions, because nobody is identified yet when these checks run.

Each attempt is counted before the password is checked, and a successful sign-in clears the count, so
parallel requests cannot all pass the check before any of them is counted. Limits are per address: a limit
per client address would need the deployment's proxy settings to be trustworthy, and is left for go-live.
"""

from datetime import timedelta

from django.conf import settings

from .db import scalar


def allow_attempt(email):
    """Count a sign-in attempt for this address. False when the address is locked and the attempt must be refused."""
    window = timedelta(seconds=settings.LOGIN_FAILURE_WINDOW_SECONDS)
    return scalar("SELECT start_login_attempt(%s, %s, %s)", [email, window, settings.LOGIN_MAX_FAILURES])


def clear(email):
    scalar("SELECT clear_login_failures(%s)", [email])
