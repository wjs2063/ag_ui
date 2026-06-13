from contextlib import asynccontextmanager
from typing import AsyncIterator

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


@asynccontextmanager
async def lifespan_checkpointer(dsn: str) -> AsyncIterator[AsyncPostgresSaver]:
    async with AsyncConnectionPool(
        conninfo=dsn,
        max_size=20,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
    ) as pool:
        saver = AsyncPostgresSaver(pool)
        await saver.setup()
        yield saver
