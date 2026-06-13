import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from langgraph.types import Command
from pydantic import BaseModel

from pocs.interrupt_pattern.checkpointer import lifespan_checkpointer
from pocs.interrupt_pattern.config import DATABASE_URL
from pocs.interrupt_pattern.graph import build_graph


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with lifespan_checkpointer(DATABASE_URL) as saver:
        app.state.graph = build_graph(saver)
        app.state.checkpointer = saver
        yield


app = FastAPI(title="LangGraph Interrupt POC", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: Any
    thread_id: str | None = None


class ChatResponse(BaseModel):
    thread_id: str
    message: Any
    done: bool = False


def _next_message(thread_id: str, result: dict) -> ChatResponse:
    if "__interrupt__" in result and result["__interrupt__"]:
        return ChatResponse(
            thread_id=thread_id,
            message=result["__interrupt__"][0].value,
            done=False,
        )
    return ChatResponse(
        thread_id=thread_id,
        message=result.get("response", ""),
        done=True,
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """Single chat endpoint.

    Server is uniform: always Command(resume=message).
      - 새 thread 에서는 resume 값이 소비되지 않고 그래프가 첫 interrupt 까지 진행
      - 진행 중 thread 에서는 노드의 interrupt() 자리로 값이 그대로 들어감
      - 완료된 thread 에서는 마지막 상태를 그대로 반환
    분기 로직은 모두 노드 안 (각 interrupt 시점의 페이로드 종류) 에 있다.
    """
    print("요청 :",req)
    thread_id = req.thread_id or str(uuid.uuid4())
    cfg = {"configurable": {"thread_id": thread_id}}
    try:
        result = await app.state.graph.ainvoke(Command(resume=req.message), cfg)
        print(result)
    except ValueError as e:
        raise HTTPException(422, detail=str(e)) from e
    return _next_message(thread_id, result)


@app.get("/state/{thread_id}")
async def get_state(thread_id: str):
    cfg = {"configurable": {"thread_id": thread_id}}
    snap = await app.state.graph.aget_state(cfg)
    return {
        "thread_id": thread_id,
        "values": {k: v for k, v in snap.values.items() if k != "messages"},
        "next": list(snap.next),
        "awaiting_input": bool(snap.tasks) and any(t.interrupts for t in snap.tasks),
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":


    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)