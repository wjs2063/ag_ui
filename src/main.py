import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.event_queue import EventQueue
from src.memory.api import extract, feedback, graph, retrieve, turns
from src.memory.layers.l1_store import L1Store
from src.memory.layers.l2_store import L2Store
from src.memory.layers.l3_store import L3Store
from src.stream import run_workflow_stream

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    event_queue = EventQueue(maxsize=1000, num_workers=1)
    await event_queue.start()
    app.state.event_queue = event_queue

    l1 = L1Store()
    await l1.ensure_indexes()
    app.state.l1_store = l1
    app.state.l2_store = L2Store()
    app.state.l3_store = L3Store()

    yield
    await event_queue.shutdown(timeout=10.0)


app = FastAPI(title="AG-UI LangGraph POC", lifespan=lifespan)

app.include_router(turns.router, prefix="/memory", tags=["memory"])
app.include_router(extract.router, prefix="/memory", tags=["memory"])
app.include_router(retrieve.router, prefix="/memory", tags=["memory"])
app.include_router(feedback.router, prefix="/memory", tags=["memory"])
app.include_router(graph.router, prefix="/memory", tags=["memory"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    query: str
    thread_id: str | None = None


@app.post("/agent")
async def run_agent(req: RunRequest):
    return StreamingResponse(
        run_workflow_stream(query=req.query, thread_id=req.thread_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class DelayedInsertRequest(BaseModel):
    data: dict


@app.post("/enqueue-delayed-insert")
async def enqueue_delayed_insert(
    req: DelayedInsertRequest,
    request: Request,
):
    eq: EventQueue = request.app.state.event_queue
    payload = req.data

    async def delayed_insert() -> None:
        await asyncio.sleep(3)
        # TODO: 실제 DB 연결로 교체
        logger.info("DB INSERT: %s", payload)

    ok = await eq.enqueue(delayed_insert)
    if not ok:
        return {"status": "error", "message": "queue full or not running"}
    return {"status": "enqueued", "pending": eq.pending}


@app.get("/health")
async def health(request: Request):
    eq: EventQueue = request.app.state.event_queue
    return {
        "status": "ok",
        "queue_pending": eq.pending,
        "queue_active": eq.active_count,
        "queue_maxsize": eq.maxsize,
    }
