import asyncio
import logging

from src.event_queue.worker import Task, run_worker

logger = logging.getLogger(__name__)


class EventQueue:
    def __init__(
        self,
        maxsize: int = 1000,
        num_workers: int = 3,
    ) -> None:
        self._queue: asyncio.Queue[Task | None] = asyncio.Queue(
            maxsize=maxsize,
        )
        self._num_workers = num_workers
        self._workers: list[asyncio.Task] = []
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        for i in range(self._num_workers):
            task = asyncio.create_task(
                run_worker(self._queue, i),
                name=f"event-queue-worker-{i}",
            )
            self._workers.append(task)
        logger.info(
            "EventQueue started with %d workers",
            self._num_workers,
        )

    async def enqueue(self, coro_fn: Task) -> bool:
        if not self._running:
            logger.warning("EventQueue is not running")
            return False
        try:
            self._queue.put_nowait(coro_fn)
            return True
        except asyncio.QueueFull:
            logger.warning(
                "EventQueue full (maxsize=%d)",
                self._queue.maxsize,
            )
            return False

    async def shutdown(self, timeout: float = 10.0) -> None:
        if not self._running:
            return
        self._running = False

        for _ in self._workers:
            try:
                self._queue.put_nowait(None)
            except asyncio.QueueFull:
                pass

        done, pending = await asyncio.wait(
            self._workers, timeout=timeout,
        )
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._workers.clear()

        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except asyncio.QueueEmpty:
                break

        logger.info("EventQueue shut down")

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    @property
    def maxsize(self) -> int:
        return self._queue.maxsize
