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
