import asyncio
import uuid

import psycopg
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from pocs.interrupt_pattern.config import DATABASE_URL


CHECKPOINT_TABLES = (
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoints",
    "checkpoint_migrations",
)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def _truncate_checkpoint_tables() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            for table in CHECKPOINT_TABLES:
                try:
                    cur.execute(f"TRUNCATE {table} RESTART IDENTITY CASCADE")
                except psycopg.errors.UndefinedTable:
                    conn.rollback()


@pytest_asyncio.fixture
async def fastapi_client():
    from pocs.interrupt_pattern.main import app

    _truncate_checkpoint_tables()
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest_asyncio.fixture
async def a2a_client_setup():
    from pocs.interrupt_pattern.a2a_server.app import build_app_with_lifespan

    _truncate_checkpoint_tables()
    app = build_app_with_lifespan()
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
def thread_id() -> str:
    return f"t-{uuid.uuid4().hex[:8]}"
