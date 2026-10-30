import pytest

from core import ports
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
    from contextlib import contextmanager

    from django.db import connection

    @contextmanager
    def switch(user):
        with connection.cursor() as cursor:
            cursor.execute("SET ROLE web")
            cursor.execute("SELECT set_config('app.user_id', %s, false)", [str(user.pk)])
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
                cursor.execute("SELECT set_config('app.user_id', '', false)")

    return switch
