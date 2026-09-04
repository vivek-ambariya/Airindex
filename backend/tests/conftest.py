from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

load_dotenv(BACKEND_DIR / ".env", override=False)


@pytest.fixture(scope="session")
def db_conn():
    """A raw connection to the configured database.

    Skips rather than fails when the server is not running: a developer
    who has not started XAMPP yet should see "skipped", not a wall of
    connection errors that looks like the code is broken.
    """
    import pymysql
    from app.db import connect

    try:
        conn = connect()
    except pymysql.err.OperationalError as exc:
        pytest.skip(f"Database not reachable ({exc}). Start XAMPP's MySQL and retry.")

    # Autocommit, so this connection sees rows the Flask test client
    # committed on its own connection. InnoDB defaults to REPEATABLE
    # READ: without this the fixture holds one snapshot for the whole
    # session and a subscription created through the API is invisible
    # here -- which reads as "the insert did not happen" rather than as
    # an isolation-level artefact.
    conn.autocommit(True)
    yield conn
    conn.close()


@pytest.fixture()
def app():
    from app import create_app
    application = create_app({"TESTING": True})
    return application


@pytest.fixture()
def client(app):
    return app.test_client()
