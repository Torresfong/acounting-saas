from django.db import migrations

from core.rls import IDENTITY_FUNCTION, IDENTITY_SETTING, WEB_ROLE

CREATE_ROLE = f"""
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{WEB_ROLE}') THEN
        CREATE ROLE {WEB_ROLE} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
    END IF;
END
$$
"""

FORWARD = [
    CREATE_ROLE,
    # The signed-in user's id as a transaction-local setting; missing or empty means nobody.
    f"""
    CREATE FUNCTION {IDENTITY_FUNCTION}() RETURNS bigint LANGUAGE sql STABLE AS
    $$ SELECT NULLIF(current_setting('{IDENTITY_SETTING}', true), '')::bigint $$
    """,
    f"GRANT USAGE ON SCHEMA public TO {WEB_ROLE}",
    # The web role starts with access to nothing and there are no default privileges, so a table is
    # reachable only when its own migration grants it (tenant tables do that through
    # core.rls.enable_tenant_rls, together with their policy). Users, jobs, sessions and Django's own
    # tables stay closed until the tickets that put them under policies open them: 02b (#32) for users,
    # 02d (#34) for jobs. The membership tables are read-only; writes come with the firm and invitation flows.
    f"GRANT SELECT ON core_company, core_companyaccess TO {WEB_ROLE}",
    "ALTER TABLE core_company ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE core_company FORCE ROW LEVEL SECURITY",
    f"""
    CREATE POLICY company_visible ON core_company FOR SELECT TO {WEB_ROLE}
    USING (id IN (SELECT company_id FROM core_companyaccess WHERE user_id = {IDENTITY_FUNCTION}()))
    """,
    "ALTER TABLE core_companyaccess ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE core_companyaccess FORCE ROW LEVEL SECURITY",
    f"""
    CREATE POLICY own_rows ON core_companyaccess FOR SELECT TO {WEB_ROLE}
    USING (user_id = {IDENTITY_FUNCTION}())
    """,
]

# The role is cluster-wide and may be shared with other databases, so reversing leaves it in place.
REVERSE = [
    f"REVOKE ALL ON core_company, core_companyaccess FROM {WEB_ROLE}",
    "DROP POLICY IF EXISTS own_rows ON core_companyaccess",
    "ALTER TABLE core_companyaccess DISABLE ROW LEVEL SECURITY",
    "DROP POLICY IF EXISTS company_visible ON core_company",
    "ALTER TABLE core_company DISABLE ROW LEVEL SECURITY",
    f"DROP FUNCTION IF EXISTS {IDENTITY_FUNCTION}()",
]


class Migration(migrations.Migration):
    dependencies = [("core", "0002_tenancy"), ("sessions", "0001_initial")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
