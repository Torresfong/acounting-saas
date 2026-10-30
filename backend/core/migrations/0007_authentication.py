from django.db import migrations

from core.rls import IDENTITY_FUNCTION, WEB_ROLE, definer_function_sql, owner_policy_sql

# Functions that run before anyone is signed in (D40 (2)). Each is SECURITY DEFINER, so it runs as the
# table owner, with a pinned search path, and each returns only what its caller needs. The web role may
# execute them and has no access to the tables behind them, apart from reading its own user row.

LOOKUP = """
CREATE FUNCTION auth_lookup(p_email text) RETURNS TABLE (id bigint, password text, is_active boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
$$ SELECT u.id, u.password, u.is_active FROM core_user u WHERE lower(u.email) = lower(p_email) LIMIT 1 $$
"""

START_ATTEMPT = """
CREATE FUNCTION start_login_attempt(p_hash text, p_window interval, p_max integer) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp AS
$$
BEGIN
    -- Attempts for one address are serialised until the request ends, so parallel requests cannot all
    -- pass the check before any of them is counted.
    PERFORM pg_advisory_xact_lock(hashtext(p_hash));
    DELETE FROM core_loginfailure WHERE at < now() - interval '1 day';
    IF (SELECT count(*) FROM core_loginfailure WHERE email_hash = p_hash AND at > now() - p_window) >= p_max THEN
        RETURN false;
    END IF;
    INSERT INTO core_loginfailure (email_hash, at) VALUES (p_hash, now());
    RETURN true;
END
$$
"""

CLEAR_FAILURES = """
CREATE FUNCTION clear_login_failures(p_hash text) RETURNS void
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp AS
$$ DELETE FROM core_loginfailure WHERE email_hash = p_hash $$
"""

FUNCTIONS = {
    "auth_lookup(text)": LOOKUP,
    "start_login_attempt(text, interval, integer)": START_ATTEMPT,
    "clear_login_failures(text)": CLEAR_FAILURES,
}

FUNCTION_FORWARD, FUNCTION_REVERSE = definer_function_sql(FUNCTIONS)

FORWARD = [
    *FUNCTION_FORWARD,
    # Sessions are served by the application's own role, so the web role needs its table. It holds a session
    # key and a signed blob that names a user id, and no tenant data.
    f"GRANT SELECT, INSERT, UPDATE, DELETE ON django_session TO {WEB_ROLE}",
    # A user may read only their own row, which Django needs to load the signed-in user. Nothing else on
    # the table is reachable by the web role; accounts are created by the functions and commands in this ticket.
    f"GRANT SELECT ON core_user TO {WEB_ROLE}",
    "ALTER TABLE core_user ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE core_user FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY own_row ON core_user FOR SELECT TO {WEB_ROLE} USING (id = {IDENTITY_FUNCTION}())",
    *owner_policy_sql("core_user"),
    # The functions above also read the membership tables, which were forced in 0003.
    *owner_policy_sql("core_company"),
    *owner_policy_sql("core_companyaccess"),
    # The throttle table is reachable only through the functions.
    "ALTER TABLE core_loginfailure ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE core_loginfailure FORCE ROW LEVEL SECURITY",
    *owner_policy_sql("core_loginfailure"),
]

REVERSE = [
    *FUNCTION_REVERSE,
    "DROP POLICY IF EXISTS definer_functions ON core_loginfailure",
    "ALTER TABLE core_loginfailure DISABLE ROW LEVEL SECURITY",
    "DROP POLICY IF EXISTS definer_functions ON core_companyaccess",
    "DROP POLICY IF EXISTS definer_functions ON core_company",
    "DROP POLICY IF EXISTS definer_functions ON core_user",
    "DROP POLICY IF EXISTS own_row ON core_user",
    "ALTER TABLE core_user DISABLE ROW LEVEL SECURITY",
    f"REVOKE ALL ON core_user FROM {WEB_ROLE}",
    f"REVOKE ALL ON django_session FROM {WEB_ROLE}",
]


class Migration(migrations.Migration):
    dependencies = [("core", "0006_login_failure"), ("sessions", "0001_initial")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
