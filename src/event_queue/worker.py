import asyncio
import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

Task = Callable[[], Awaitable[Any]]


async def run_worker(
    queue: asyncio.Queue[Task | None],
    worker_id: int,
) -> None:
    logger.info("Worker %d started", worker_id)
    while True:
        task_fn = await queue.get()
        try:
            if task_fn is None:
                break
            await task_fn()
            logger.info("Worker %d task completed", worker_id)
        except Exception:
            logger.exception("Worker %d task failed", worker_id)
        finally:
            queue.task_done()
    logger.info("Worker %d stopped", worker_id)
