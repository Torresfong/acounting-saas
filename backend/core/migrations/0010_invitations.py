from django.db import migrations

from core.rls import IDENTITY_FUNCTION, definer_function_sql

# Invitations (D40 (5), D48). Creating one checks, inside the database, that the signed-in user owns the
# company, so the rule does not rest on the view alone; the role of the invitee is fixed to staff here, not
# taken from the caller. Accepting one runs before anyone is signed in and creates the account and its
# membership in a single transaction.

CREATE_INVITATION = f"""
CREATE FUNCTION create_invitation(p_token_hash text, p_email text, p_company bigint, p_expires timestamptz)
RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp AS
$$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM core_companyaccess
        WHERE user_id = {IDENTITY_FUNCTION}() AND company_id = p_company AND role = 'owner'
    ) THEN
        RAISE EXCEPTION 'only the owner of the company may invite' USING ERRCODE = '42501';
    END IF;
    -- At most 20 invitations a day per company, so the form cannot be used to send mail in bulk.
    IF (SELECT count(*) FROM core_authtoken
        WHERE company_id = p_company AND purpose = 'invite' AND created_at > now() - interval '1 day') >= 20 THEN
        RAISE EXCEPTION 'too many invitations today' USING ERRCODE = '54000';
    END IF;
    -- An address that already has an account gets no invitation, and the caller is not told, so an owner
    -- cannot use the form to find out who is registered with another company.
    IF EXISTS (SELECT 1 FROM core_user WHERE lower(email) = lower(p_email)) THEN
        RETURN false;
    END IF;
    INSERT INTO core_authtoken (purpose, token_hash, email, company_id, role, user_id, expires_at, created_at)
    VALUES ('invite', p_token_hash, lower(p_email), p_company, 'staff', NULL, p_expires, now());
    RETURN true;
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

FORWARD, REVERSE = definer_function_sql(FUNCTIONS)

class Migration(migrations.Migration):
    dependencies = [("core", "0009_password_reset")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
