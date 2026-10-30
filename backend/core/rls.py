"""Row-level security for tenant tables (D11, D40; see docs/architecture/tenancy.md).

Every business table carries a company id. A row is visible and writable only when that company is among
the signed-in user's `CompanyAccess` rows. The signed-in user reaches the database as a transaction-local
setting (`app.user_id`), and requests run as the `web` role, which is neither table owner nor superuser.

To add a tenant table: subclass `core.models.TenantModel`, then in the migration that creates it add
`enable_tenant_rls("app_table")` after the CreateModel.
"""

from django.db import migrations

WEB_ROLE = "web"
IDENTITY_SETTING = "app.user_id"
IDENTITY_FUNCTION = "app_user_id"

_ACCESSIBLE_COMPANIES = f"SELECT company_id FROM core_companyaccess WHERE user_id = {IDENTITY_FUNCTION}()"


def tenant_policy_sql(table):
    """SQL that puts `table` under the standard isolation policy."""
    check = f"company_id IN ({_ACCESSIBLE_COMPANIES})"
    return [
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {WEB_ROLE}",
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"CREATE POLICY tenant_isolation ON {table} TO {WEB_ROLE} USING ({check}) WITH CHECK ({check})",
    ]


def drop_tenant_policy_sql(table):
    return [
        f"DROP POLICY IF EXISTS tenant_isolation ON {table}",
        f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY",
        f"REVOKE ALL ON {table} FROM {WEB_ROLE}",
    ]


def enable_tenant_rls(table):
    """A migration operation that applies the standard isolation policy to `table`."""
    return migrations.RunSQL(tenant_policy_sql(table), drop_tenant_policy_sql(table))


def owner_policy_sql(table):
    """SQL that lets the role running the migration (the table owner) through `FORCE ROW LEVEL SECURITY`.

    The SECURITY DEFINER functions of D40 (2) run as that role, and forced row-level security would
    otherwise hide every row from them. The policy names the owner explicitly, so it opens nothing to the
    web role or to a login role that is a member of it.
    """
    return [
        "DO $$ BEGIN EXECUTE format("
        f"'CREATE POLICY definer_functions ON {table} TO %I USING (true) WITH CHECK (true)', current_user); "
        "END $$"
    ]


def definer_function_sql(functions):
    """Forward and reverse SQL for SECURITY DEFINER functions: create each, close it to everyone, open it to `web`.

    `functions` maps a signature such as "auth_lookup(text)" to its CREATE FUNCTION statement.
    """
    forward, reverse = [], []
    for signature, create in functions.items():
        forward += [
            create,
            f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC",
            f"GRANT EXECUTE ON FUNCTION {signature} TO {WEB_ROLE}",
        ]
        reverse.insert(0, f"DROP FUNCTION IF EXISTS {signature}")
    return forward, reverse
