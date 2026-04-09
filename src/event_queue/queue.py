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
        self._active_tasks: list[int] = [0]

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        for i in range(self._num_workers):
            task = asyncio.create_task(
                run_worker(self._queue, i, self._active_tasks),
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

        # Phase 1: drain — 큐의 모든 Task 처리 대기
        drain_timeout = timeout * 0.6
        try:
            await asyncio.wait_for(
                self._queue.join(), timeout=drain_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Drain timed out after %.1fs, %d tasks pending",
                drain_timeout,
                self._queue.qsize(),
            )

        # drain 실패 시 남은 Task 제거 및 로깅
        dropped = 0
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
                dropped += 1
            except asyncio.QueueEmpty:
                break
        if dropped:
            logger.warning("Dropped %d undrained tasks", dropped)

        # Phase 2: sentinel 전송 후 워커 종료
        for _ in self._workers:
            await self._queue.put(None)

        stop_timeout = timeout * 0.4
        done, pending = await asyncio.wait(
            self._workers, timeout=stop_timeout,
        )
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._workers.clear()
        logger.info("EventQueue shut down")

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    @property
    def active_count(self) -> int:
        return self._active_tasks[0]

    @property
    def maxsize(self) -> int:
        return self._queue.maxsize
