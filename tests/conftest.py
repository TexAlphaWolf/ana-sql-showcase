from __future__ import annotations

import os
from collections.abc import Iterator

import psycopg
import pytest

from sqlshow import db
from sqlshow.datagen import Dataset, generate

SCALE = float(os.environ.get("SQLSHOW_TEST_SCALE", "0.02"))  # other values and seeds: a wider check
SEED = int(os.environ.get("SQLSHOW_TEST_SEED", "7"))
DSN_ENV = "SQLSHOW_TEST_DSN"


@pytest.fixture(scope="session")
def dsn() -> str:
    value = os.environ.get(DSN_ENV)
    if not value:
        pytest.skip(f"set {DSN_ENV} to a PostgreSQL database that the tests may use (schema 'sqlshow' is rebuilt)")
    return value


@pytest.fixture(scope="session")
def data() -> Dataset:
    return generate(SCALE, SEED)


@pytest.fixture(scope="session")
def conn(dsn: str, data: Dataset) -> Iterator[psycopg.Connection]:
    c = db.connect(dsn)
    db.create_schema(c)
    db.load(c, data)
    yield c
    c.close()


@pytest.fixture
def restore(conn: psycopg.Connection, data: Dataset) -> Iterator[None]:
    """For tests that rebuild the schema: put the standard data back afterwards."""
    yield
    db.create_schema(conn)
    db.load(conn, data)
