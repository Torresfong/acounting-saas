"""The audit trail (D40 (6)): who did what, to which record, when.

Create, update and delete events on business tables are written by a database trigger, so application code
cannot forget or bypass them (`enable_audit` in a table's migration). Sign-in events go through
`record_auth_event`. Domain events that are not a row change, such as an approval, are written with `record`.
Entries hold the names of changed fields and never their values; nothing here may be given a credential,
a token or a customer's details.
"""

from django.db import migrations

from .db import scalar
from .models import AuditEntry


def record_auth_event(action, email=None):
    """Write a sign-in event for each company the account belongs to. Nothing is written for an unknown address.

    Pass the address for a sign-in (the person is not identified yet); leave it out for a sign-out.
    """
    scalar("SELECT record_auth_event(%s, %s)", [action, email])


def record(action, company, actor, target_type="", target_id="", changed_fields=()):
    """Write a domain event as the signed-in user, for example an approval. Row changes are audited by trigger instead."""
    return AuditEntry.objects.create(
        company=company,
        actor_id=actor.pk,
        actor_email=actor.email,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        changed_fields=list(changed_fields),
    )


def audit_trigger_sql(table):
    """SQL that puts `table` under the audit trigger. The table needs `id` and `company_id` columns.

    The first statement refuses a table without them: the trigger would otherwise fail on the first write
    and block it.
    """
    return [
        "DO $$ BEGIN IF (SELECT count(*) FROM information_schema.columns WHERE table_schema = current_schema() "
        f"AND table_name = '{table}' AND column_name IN ('id', 'company_id')) < 2 THEN "
        f"RAISE EXCEPTION 'cannot audit {table}: it needs id and company_id columns'; END IF; END $$",
        f"CREATE TRIGGER audit_changes AFTER INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION audit_row_change()"]


def drop_audit_trigger_sql(table):
    return [f"DROP TRIGGER IF EXISTS audit_changes ON {table}"]


def enable_audit(table):
    """A migration operation that audits every insert, update and delete on `table`.

    Add it after `enable_tenant_rls` in the migration that creates a business table.
    """
    return migrations.RunSQL(audit_trigger_sql(table), drop_audit_trigger_sql(table))
