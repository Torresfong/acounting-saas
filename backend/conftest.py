from contextlib import contextmanager

import pytest
from django.db import connection

from core import ports
from core.rls import IDENTITY_SETTING, WEB_ROLE
from core.ports.fakes import FakePorts


@pytest.fixture(autouse=True)
def fake_ports():
    """Install fakes for the four external ports for every test."""
    fakes = FakePorts()
    ports.install(fakes)
    yield fakes
    ports.uninstall()


@pytest.fixture
def as_user(db):
    """Run a block as the `web` database role with the given user as the signed-in identity.

    Independent of the production middleware on purpose: it sets the role and identity with plain SQL, so
    the policies can be tested without a request. Fixtures are created before entering the block, as the
    table owner, because the web role cannot write to the membership tables.
    """
    @contextmanager
    def switch(user):
        with connection.cursor() as cursor:
            cursor.execute(f"SET ROLE {WEB_ROLE}")
            cursor.execute("SELECT set_config(%s, %s, false)", [IDENTITY_SETTING, str(user.pk)])
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
                cursor.execute("SELECT set_config(%s, '', false)", [IDENTITY_SETTING])

    return switch


@pytest.fixture
def as_production_connection(db):
    """Make the whole connection behave like production: a login role that is only a member of `web`.

    Unlike `as_user`, this changes who the connection is, not just the current role, so the session and
    authentication lookups that run before the tenant middleware are subject to the same privileges as
    everything else. Create fixtures first, then enter the block.
    """

    @contextmanager
    def switch():
        with connection.cursor() as cursor:
            cursor.execute(
                "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_test') THEN "
                f"CREATE ROLE app_test LOGIN NOSUPERUSER NOBYPASSRLS IN ROLE {WEB_ROLE}; END IF; END $$"
            )
            cursor.execute("SET SESSION AUTHORIZATION app_test")
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET SESSION AUTHORIZATION")

    return switch
