"""Run only against an ALREADY RUNNING isolated database supplied by its operator."""

import os
from pathlib import Path
from uuid import uuid4

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
def postgres_settings():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL missing: no real PostgreSQL service was started")
    # Pytest prints fixture values on failure; Settings hides the connection URL in repr.
    return Settings(database_url=url)


def test_health_uses_real_postgres(postgres_settings):
    with TestClient(create_app(postgres_settings)) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"


def test_migration_and_data_survive_application_recreation(postgres_settings, monkeypatch):
    # This may change migration state: the connection MUST point to an isolated test DB.
    monkeypatch.setenv("DATABASE_URL", postgres_settings.database_url)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    with psycopg.connect(postgres_settings.database_url) as connection:
        table = psycopg.sql.Identifier(f"studyloop_persistence_test_{uuid4().hex}")
        try:
            connection.execute(psycopg.sql.SQL("CREATE TABLE {} (value text)").format(table))
            connection.execute(
                psycopg.sql.SQL("INSERT INTO {} VALUES (%s)").format(table), ("retained",)
            )
            connection.commit()
            for _ in range(2):
                command.upgrade(config, "head")
                # Separate application lifetimes; real systemd/DB restarts remain manual TC-05.
                with TestClient(create_app(postgres_settings)) as client:
                    assert client.get("/api/v1/health").status_code == 200
                with psycopg.connect(postgres_settings.database_url) as reader:
                    assert reader.execute("SELECT version_num FROM alembic_version").fetchall() == [
                        (ScriptDirectory.from_config(config).get_current_head(),)
                    ]
                    assert reader.execute(
                        psycopg.sql.SQL("SELECT value FROM {}").format(table)
                    ).fetchall() == [("retained",)]
        finally:
            connection.rollback()
            connection.execute(psycopg.sql.SQL("DROP TABLE IF EXISTS {}").format(table))
            connection.commit()
