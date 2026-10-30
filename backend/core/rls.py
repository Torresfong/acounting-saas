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


def tenant_policy_sql(table, column="company_id"):
    """SQL that puts `table` under the standard isolation policy."""
    check = f"{column} IN ({_ACCESSIBLE_COMPANIES})"
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


def enable_tenant_rls(table, column="company_id"):
    """A migration operation that applies the standard isolation policy to `table`."""
    return migrations.RunSQL(tenant_policy_sql(table, column), drop_tenant_policy_sql(table))
