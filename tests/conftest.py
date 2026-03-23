"""Shared pytest fixtures."""
import pytest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.config import cfg
from backend.rooms import ROOMS
from backend.digital_twin import DigitalTwin
from backend.memory import init_db

@pytest.fixture(scope="session")
def test_db(tmp_path_factory):
    """Temp SQLite DB for tests."""
    import os
    db = tmp_path_factory.mktemp("data") / "test.db"
    os.environ["PLANTAOS_TEST_DB"] = str(db)
    init_db()
    return db

@pytest.fixture
def twin():
    t = DigitalTwin()
    t.initialize(month=3, hour=9)
    return t

@pytest.fixture
def rooms():
    return ROOMS

@pytest.fixture
def cfg_fixture():
    return cfg
