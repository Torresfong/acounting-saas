from django.db import migrations

from core.rls import definer_function_sql, owner_policy_sql

# Token functions run before anyone is signed in, as the table owner (see 0007). The tokens table is
# reachable only through them.

TOKEN_IS_VALID = """
CREATE FUNCTION token_is_valid(p_token_hash text, p_purpose text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp AS
$$
    SELECT EXISTS (
        SELECT 1 FROM core_authtoken
        WHERE token_hash = p_token_hash AND purpose = p_purpose AND used_at IS NULL AND expires_at > now()
    )
$$
"""

CREATE_PASSWORD_RESET = """
CREATE FUNCTION create_password_reset(p_token_hash text, p_email text, p_expires timestamptz) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp AS
$$
DECLARE
    v_user bigint;
BEGIN
    DELETE FROM core_authtoken WHERE expires_at < now() - interval '30 days';
    SELECT id INTO v_user FROM core_user WHERE lower(email) = lower(p_email) AND is_active;
    IF v_user IS NULL THEN
        RETURN false;
    END IF;
    -- At most three links an hour per account, so the form cannot be used to flood a mailbox.
    IF (SELECT count(*) FROM core_authtoken
        WHERE user_id = v_user AND purpose = 'reset' AND created_at > now() - interval '1 hour') >= 3 THEN
        RETURN false;
    END IF;
    INSERT INTO core_authtoken (purpose, token_hash, email, role, user_id, expires_at, created_at)
    VALUES ('reset', p_token_hash, lower(p_email), '', v_user, LEAST(p_expires, now() + interval '1 hour'), now());
    RETURN true;
END
$$
"""

COMPLETE_PASSWORD_RESET = """
CREATE FUNCTION complete_password_reset(p_token_hash text, p_password_hash text) RETURNS bigint
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp AS
$$
DECLARE
    v_token bigint;
    v_user bigint;
BEGIN
    IF p_password_hash !~ '^argon2[$]argon2(id|i|d)[$]v=' THEN
        RAISE EXCEPTION 'not an Argon2 password hash' USING ERRCODE = '22023';
    END IF;
    SELECT t.id, t.user_id INTO v_token, v_user
    FROM core_authtoken t JOIN core_user u ON u.id = t.user_id
    WHERE t.token_hash = p_token_hash AND t.purpose = 'reset' AND t.used_at IS NULL AND t.expires_at > now()
      AND u.is_active
    FOR UPDATE OF t;
    IF v_token IS NULL THEN
        RAISE EXCEPTION 'invalid or expired link' USING ERRCODE = '28000';
    END IF;
    UPDATE core_user SET password = p_password_hash WHERE id = v_user;
    -- Every other reset link for this account stops working as well.
    UPDATE core_authtoken SET used_at = now()
    WHERE user_id = v_user AND purpose = 'reset' AND used_at IS NULL;
    RETURN v_user;
END
$$
"""

FUNCTIONS = {
    "token_is_valid(text, text)": TOKEN_IS_VALID,
    "create_password_reset(text, text, timestamptz)": CREATE_PASSWORD_RESET,
    "complete_password_reset(text, text)": COMPLETE_PASSWORD_RESET,
}

FUNCTION_FORWARD, FUNCTION_REVERSE = definer_function_sql(FUNCTIONS)

FORWARD = [
    "ALTER TABLE core_authtoken ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE core_authtoken FORCE ROW LEVEL SECURITY",
    *owner_policy_sql("core_authtoken"),
    *FUNCTION_FORWARD,
]
REVERSE = [
    *FUNCTION_REVERSE,
    "DROP POLICY IF EXISTS definer_functions ON core_authtoken",
    "ALTER TABLE core_authtoken DISABLE ROW LEVEL SECURITY",
]


class Migration(migrations.Migration):
    dependencies = [("core", "0008_auth_token")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
