from django.contrib.auth import login


def complete_sign_in(request, user):
    """The single place where a verified user becomes a signed-in session.

    Two-factor authentication will plug in here (D40 (7)): a second check can run before `login`.
    """
    login(request, user, backend="core.auth.EmailBackend")
