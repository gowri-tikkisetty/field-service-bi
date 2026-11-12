import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DB = ROOT / "data" / "field_service.db"


@pytest.fixture(scope="session")
def db():
    if not DB.exists():
        pytest.exit("Run `python scripts/build_db.py` first to create the demo database.")
    con = sqlite3.connect(DB)
    yield con
    con.close()


@pytest.fixture(scope="session")
def client():
    from app.app import create_app
    return create_app().test_client()
