"""The audit trail's guarantees at the database seam: who can write, change and read what."""

import pytest
from django.db import DatabaseError, connection, transaction

from core.models import AuditEntry

from .factories import make_company, make_member
from .test_tenancy import query


@pytest.fixture
def entries(world):
    acme_entry = AuditEntry.objects.create(company=world["acme"], actor_id=1, actor_email="a@x", action="create")
    beta_entry = AuditEntry.objects.create(company=world["beta"], actor_id=2, actor_email="b@x", action="create")
    return acme_entry, beta_entry


def test_the_web_role_can_read_only_its_own_companies_entries(as_user, world, entries):
    with as_user(world["acme_owner"]):
        assert query("SELECT count(*) FROM core_auditentry") == [(1,)]
    with as_user(world["accountant"]):
        assert query("SELECT count(*) FROM core_auditentry") == [(2,)]


ADD_ENTRY = (
    "INSERT INTO core_auditentry (company_id, actor_email, action, target_type, target_id, changed_fields) "
    "VALUES (%s, '', 'create', '', '', '[]') RETURNING id"
)


def test_the_web_role_can_add_an_entry_for_its_own_company_but_not_another_or_none(as_user, world):
    with as_user(world["acme_owner"]):
        query(ADD_ENTRY, [world["acme"].pk])
        for company in [world["beta"].pk, None]:
            with pytest.raises(DatabaseError), transaction.atomic():
                query(ADD_ENTRY, [company])


@pytest.mark.parametrize("statement", ["UPDATE core_auditentry SET action = 'login'", "DELETE FROM core_auditentry", "TRUNCATE core_auditentry"])
def test_the_web_role_cannot_change_delete_or_truncate_entries(as_user, world, entries, statement):
    with as_user(world["acme_owner"]), pytest.raises(DatabaseError), transaction.atomic():
        query(statement)


def test_even_the_owner_connection_cannot_rewrite_or_delete_an_entry(world, entries):
    with pytest.raises(DatabaseError, match="cannot be changed or deleted"), transaction.atomic():
        AuditEntry.objects.update(action="login")
    with pytest.raises(DatabaseError, match="cannot be changed or deleted"), transaction.atomic():
        AuditEntry.objects.all().delete()

    assert AuditEntry.objects.count() == 2


def test_only_sign_in_events_can_be_recorded_through_the_sign_in_function(as_user, world):
    with as_user(world["acme_owner"]), pytest.raises(DatabaseError), transaction.atomic():
        query("SELECT record_auth_event('create', NULL)")


def test_the_sign_in_function_writes_one_entry_per_company_for_an_accountant(world):
    query("SELECT record_auth_event('login', %s)", [world["accountant"].email])

    assert sorted(AuditEntry.objects.values_list("company_id", flat=True)) == sorted([world["acme"].pk, world["beta"].pk])


def test_an_unknown_address_writes_nothing(world):
    query("SELECT record_auth_event('login_failed', 'nobody@nowhere.example')")

    assert AuditEntry.objects.count() == 0


def test_an_account_with_no_company_writes_nothing(db):
    from .factories import make_user

    make_user("loner@example.com")
    query("SELECT record_auth_event('login', 'loner@example.com')")

    assert AuditEntry.objects.count() == 0
