"""Run only against an ALREADY RUNNING isolated database supplied by its operator."""

import os
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient

from studyloop.main import create_app
from studyloop.settings import Settings

pytestmark = pytest.mark.postgres


@pytest.fixture
def postgres_url():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL missing: no real PostgreSQL service was started")
    return url


def test_health_uses_real_postgres(postgres_url):
    with TestClient(create_app(Settings(database_url=postgres_url))) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"


def test_initial_migration_is_repeatable(postgres_url, monkeypatch):
    # This may change migration state: the connection MUST point to an isolated test DB.
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    with psycopg.connect(postgres_url) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchall() == [
            (ScriptDirectory.from_config(config).get_current_head(),)
        ]
