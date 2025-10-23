import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlmodel import SQLModel

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TEMP_DATA_DIR = Path(tempfile.mkdtemp())
os.environ["DATA_DIR"] = str(TEMP_DATA_DIR)

from backend.app import config as config_module  # noqa: E402
from backend.app import database as database_module  # noqa: E402
from backend.app import models as models_module  # noqa: E402
from backend.app.services import monitor as monitor_module  # noqa: E402

database_module.init_db()


def reset_database() -> None:
    SQLModel.metadata.drop_all(database_module.database_engine)
    SQLModel.metadata.create_all(database_module.database_engine)


def create_host() -> models_module.Host:
    with database_module.get_session() as session:
        host = models_module.Host(name="Test Host", base_url="http://example.com")
        session.add(host)
        session.commit()
        session.refresh(host)
        return host


@pytest.fixture(autouse=True)
def clean_database() -> None:
    reset_database()
    yield


@pytest.fixture()
def config_manager() -> config_module.ConfigManager:
    return config_module.ConfigManager()


def test_create_host_check_skips_duplicate_scheduled(config_manager):
    host = create_host()

    check1, created1 = monitor_module.create_host_check(host.id, "scheduled", config_manager)
    assert created1 is True
    assert check1.finished_at is None

    check2, created2 = monitor_module.create_host_check(host.id, "scheduled", config_manager)
    assert created2 is False
    assert check1.id == check2.id

    with database_module.get_session() as session:
        db_check = session.get(models_module.HostCheck, check1.id)
        db_check.status = "success"
        db_check.finished_at = datetime.now(timezone.utc)
        session.add(db_check)
        session.commit()

    check3, created3 = monitor_module.create_host_check(host.id, "scheduled", config_manager)
    assert created3 is True
    assert check3.id != check1.id


def test_create_host_check_manual_always_creates_new(config_manager):
    host = create_host()

    first, created_first = monitor_module.create_host_check(host.id, "manual", config_manager)
    second, created_second = monitor_module.create_host_check(host.id, "manual", config_manager)

    assert created_first is True
    assert created_second is True
    assert first.id != second.id
