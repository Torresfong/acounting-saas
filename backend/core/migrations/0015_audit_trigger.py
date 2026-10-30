from django.db import migrations

from core.rls import IDENTITY_FUNCTION

# The shared trigger function behind `core.audit.enable_audit`. It runs with the rights of whoever makes the
# change, not as the owner: a signed-in user writes their own entry under the same row-level security as any
# other insert, so a change to a company the user cannot reach cannot be recorded either. Only the names of
# changed fields are stored, never values.
AUDIT_ROW_CHANGE = f"""
CREATE FUNCTION audit_row_change() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, public, pg_temp AS
$$
DECLARE
    v_row jsonb;
    v_fields jsonb := '[]'::jsonb;
    v_email text;
BEGIN
    IF TG_OP = 'DELETE' THEN
        v_row := to_jsonb(OLD);
    ELSE
        v_row := to_jsonb(NEW);
    END IF;
    IF TG_OP = 'UPDATE' THEN
        SELECT coalesce(jsonb_agg(n.key ORDER BY n.key), '[]'::jsonb) INTO v_fields
        FROM jsonb_each(to_jsonb(NEW)) AS n WHERE n.value IS DISTINCT FROM (to_jsonb(OLD) -> n.key);
        IF v_fields = '[]'::jsonb THEN
            RETURN NULL;
        END IF;
    END IF;
    SELECT email INTO v_email FROM core_user WHERE id = {IDENTITY_FUNCTION}();
    INSERT INTO core_auditentry (company_id, actor_id, actor_email, action, target_type, target_id, changed_fields, occurred_at)
    VALUES (
        (v_row ->> 'company_id')::bigint,
        {IDENTITY_FUNCTION}(),
        coalesce(v_email, ''),
        CASE TG_OP WHEN 'INSERT' THEN 'create' WHEN 'UPDATE' THEN 'update' ELSE 'delete' END,
        TG_TABLE_NAME,
        v_row ->> 'id',
        v_fields,
        now()
    );
    RETURN NULL;
END
$$
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0014_audit_trail")]
    operations = [migrations.RunSQL([AUDIT_ROW_CHANGE], ["DROP FUNCTION IF EXISTS audit_row_change()"])]
