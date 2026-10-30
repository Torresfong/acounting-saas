from django.db import migrations

from core.rls import IDENTITY_FUNCTION, WEB_ROLE, definer_function_sql, owner_policy_sql

# The audit trail (D40 (6)). Company isolation is row-level security, like every tenant table; unlike
# them, the web role may only read and insert. A trigger refuses updates, deletes and truncation from every
# other role as well, so nothing in the application can rewrite history.

ACCESSIBLE = f"company_id IN (SELECT company_id FROM core_companyaccess WHERE user_id = {IDENTITY_FUNCTION}())"

APPEND_ONLY_FUNCTION = """
CREATE FUNCTION audit_entries_are_append_only() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, public, pg_temp AS
$$
BEGIN
    RAISE EXCEPTION 'audit entries cannot be changed or deleted' USING ERRCODE = '23001';
END
$$
"""

# Sign-in events happen before anyone is identified (a failed sign-in never is), so they go through a
# definer function like the other pre-sign-in operations. It writes one entry for each company the account
# belongs to. An address with no account has nothing to attach the entry to and writes nothing.
RECORD_AUTH_EVENT = """
CREATE FUNCTION record_auth_event(p_action text, p_email text DEFAULT NULL) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp AS
$$
DECLARE
    v_user bigint;
    v_email text;
BEGIN
    IF p_action NOT IN ('login', 'login_failed', 'logout') THEN
        RAISE EXCEPTION 'not a sign-in event' USING ERRCODE = '22023';
    END IF;
    IF p_email IS NULL THEN
        SELECT id, email INTO v_user, v_email FROM core_user WHERE id = app_user_id();
    ELSE
        SELECT id, email INTO v_user, v_email FROM core_user WHERE lower(email) = lower(p_email);
    END IF;
    IF v_user IS NULL THEN
        RETURN;
    END IF;
    INSERT INTO core_auditentry (company_id, actor_id, actor_email, action, target_type, target_id, changed_fields, occurred_at)
    SELECT a.company_id, v_user, v_email, p_action, 'user', v_user::text, '[]'::jsonb, now()
    FROM core_companyaccess a WHERE a.user_id = v_user;
END
$$
"""

FUNCTION_FORWARD, FUNCTION_REVERSE = definer_function_sql({"record_auth_event(text, text)": RECORD_AUTH_EVENT})

FORWARD = [
    APPEND_ONLY_FUNCTION,
    "CREATE TRIGGER audit_rows_are_append_only BEFORE UPDATE OR DELETE ON core_auditentry "
    "FOR EACH ROW EXECUTE FUNCTION audit_entries_are_append_only()",
    f"GRANT SELECT, INSERT ON core_auditentry TO {WEB_ROLE}",
    "ALTER TABLE core_auditentry ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE core_auditentry FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY company_entries ON core_auditentry FOR SELECT TO {WEB_ROLE} USING ({ACCESSIBLE})",
    f"CREATE POLICY company_inserts ON core_auditentry FOR INSERT TO {WEB_ROLE} WITH CHECK ({ACCESSIBLE})",
    *owner_policy_sql("core_auditentry"),
    *FUNCTION_FORWARD,
]

REVERSE = [
    *FUNCTION_REVERSE,
    "DROP POLICY IF EXISTS definer_functions ON core_auditentry",
    "DROP POLICY IF EXISTS company_inserts ON core_auditentry",
    "DROP POLICY IF EXISTS company_entries ON core_auditentry",
    "ALTER TABLE core_auditentry DISABLE ROW LEVEL SECURITY",
    f"REVOKE ALL ON core_auditentry FROM {WEB_ROLE}",
    "DROP TRIGGER IF EXISTS audit_rows_are_append_only ON core_auditentry",
    "DROP FUNCTION IF EXISTS audit_entries_are_append_only()",
]


class Migration(migrations.Migration):
    dependencies = [("core", "0013_audit_entry")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
