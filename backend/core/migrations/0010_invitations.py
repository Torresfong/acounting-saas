from django.db import migrations

from core.rls import IDENTITY_FUNCTION, WEB_ROLE

# Invitations (D40 (5), D48). Creating one checks, inside the database, that the signed-in user owns the
# company, so the rule does not rest on the view alone; the role of the invitee is fixed to staff here, not
# taken from the caller. Accepting one runs before anyone is signed in and creates the account and its
# membership in a single transaction.

CREATE_INVITATION = f"""
CREATE FUNCTION create_invitation(p_token_hash text, p_email text, p_company bigint, p_expires timestamptz)
RETURNS void LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp AS
$$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM core_companyaccess
        WHERE user_id = {IDENTITY_FUNCTION}() AND company_id = p_company AND role = 'owner'
    ) THEN
        RAISE EXCEPTION 'only the owner of the company may invite' USING ERRCODE = '42501';
    END IF;
    IF EXISTS (SELECT 1 FROM core_user WHERE lower(email) = lower(p_email)) THEN
        RAISE EXCEPTION 'that address already has an account' USING ERRCODE = '23505';
    END IF;
    INSERT INTO core_authtoken (purpose, token_hash, email, company_id, role, user_id, expires_at, created_at)
    VALUES ('invite', p_token_hash, lower(p_email), p_company, 'staff', NULL, p_expires, now());
END
$$
"""

ACCEPT_INVITATION = """
CREATE FUNCTION accept_invitation(p_token_hash text, p_password_hash text) RETURNS bigint
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp AS
$$
DECLARE
    v_token bigint;
    v_email text;
    v_company bigint;
    v_role text;
    v_user bigint;
BEGIN
    SELECT id, email, company_id, role INTO v_token, v_email, v_company, v_role FROM core_authtoken
    WHERE token_hash = p_token_hash AND purpose = 'invite' AND used_at IS NULL AND expires_at > now()
    FOR UPDATE;
    IF v_token IS NULL THEN
        RAISE EXCEPTION 'invalid or expired link' USING ERRCODE = '28000';
    END IF;
    INSERT INTO core_user (password, last_login, is_superuser, email, is_active, date_joined)
    VALUES (p_password_hash, NULL, false, v_email, true, now())
    RETURNING id INTO v_user;
    INSERT INTO core_companyaccess (user_id, company_id, role, created_at)
    VALUES (v_user, v_company, v_role, now());
    UPDATE core_authtoken SET used_at = now() WHERE id = v_token;
    RETURN v_user;
END
$$
"""

FUNCTIONS = {
    "create_invitation(text, text, bigint, timestamptz)": CREATE_INVITATION,
    "accept_invitation(text, text)": ACCEPT_INVITATION,
}

FORWARD = []
REVERSE = []
for signature, create in FUNCTIONS.items():
    FORWARD += [create, f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC", f"GRANT EXECUTE ON FUNCTION {signature} TO {WEB_ROLE}"]
    REVERSE.append(f"DROP FUNCTION IF EXISTS {signature}")


class Migration(migrations.Migration):
    dependencies = [("core", "0009_password_reset")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
