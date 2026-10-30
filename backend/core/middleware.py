from django.db import connection, transaction

from .rls import IDENTITY_SETTING, WEB_ROLE


class TenantContextMiddleware:
    """Run every request as the `web` database role, with the signed-in user as the database identity.

    Both are transaction-local: the request is wrapped in a transaction, `SET LOCAL ROLE` drops the
    connection to the role that row-level security applies to, and the user id is set the same way, so
    nothing carries over to the next request on a pooled connection. Anonymous requests get an empty
    identity, which matches no company. Place it after AuthenticationMiddleware.

    When the request is already inside an outer transaction (tests), releasing the request's savepoint
    does not undo SET LOCAL, so the role and identity are reset explicitly on the normal path. If the
    request fails, the rollback undoes them, and running more SQL in the failed transaction would only
    hide the original error.

    Limits are documented in docs/architecture/tenancy.md: the web role can still change its own setting,
    and a streaming response is read after this middleware returns, outside the role.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        user_id = str(user.pk) if user is not None and user.is_authenticated else ""

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(f"SET LOCAL ROLE {WEB_ROLE}")
                cursor.execute("SELECT set_config(%s, %s, true)", [IDENTITY_SETTING, user_id])
            response = self.get_response(request)
            if not connection.needs_rollback:
                with connection.cursor() as cursor:
                    cursor.execute("RESET ROLE")
                    cursor.execute("SELECT set_config(%s, '', true)", [IDENTITY_SETTING])
            return response
