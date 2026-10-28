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
