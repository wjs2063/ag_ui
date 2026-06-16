import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from pydantic import BaseModel

from pocs.interrupt_pattern.checkpointer import lifespan_checkpointer
from pocs.interrupt_pattern.config import DATABASE_URL
from pocs.interrupt_pattern.graph import build_orchestrator_graph


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with lifespan_checkpointer(DATABASE_URL) as saver:
        app.state.orchestrator = build_orchestrator_graph(saver)
        yield


app = FastAPI(title="LangGraph Interrupt POC", lifespan=lifespan)


class UserMessage(BaseModel):
    question: str
    metadata: dict[str, Any] = {}


class ChatRequest(BaseModel):
    message: UserMessage  # {"question": "...", "metadata": {...}} 형태 강제
    thread_id: str | None = None


class ChatResponse(BaseModel):
    thread_id: str
    message: Any


class EventRequest(BaseModel):
    event: str
    thread_id: str


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """client → 서버 → A2A(LLM, 항상 input_required) → interrupt → client 의 무한 루프.

    thread_id 는 클라이언트 고유 ID 처럼 고정. 그래프는 END 로 끝나지 않고 매 턴
    interrupt 에서 멈춰 다음 메시지를 기다리므로 같은 thread_id 로 대화가 계속된다.
    """
    thread_id = req.thread_id or str(uuid.uuid4())
    print(f"\n[CLIENT → 서버] message={req.message}  thread_id={thread_id}")
    cfg = {"configurable": {"thread_id": thread_id}}
    orch = app.state.orchestrator

    snap = await orch.aget_state(cfg)
    if snap.next:  # interrupt 대기 중 → 답으로 재개
        result = await orch.ainvoke(Command(resume=req.message.model_dump()), cfg)
    else:  # 새 대화/idle → 첫 메시지를 입력으로 시작(버려지지 않음)
        result = await orch.ainvoke(
            {"messages": [HumanMessage(content=req.message.question)]}, cfg
        )

    reply = result["__interrupt__"][0].value
    print(f"[서버 → CLIENT] message={reply}")
    return ChatResponse(thread_id=thread_id, message=reply)


@app.post("/event")
async def device_event(req: EventRequest):
    """단말 이벤트: interrupt 를 재개하지 않고 history 만 갱신한다(맥락 공유).

    resume(Command) 을 호출하지 않으므로 펜딩 interrupt 는 그대로 보존되고,
    다음 /chat 요청에서 정상적으로 재개된다.
    """
    cfg = {"configurable": {"thread_id": req.thread_id}}
    orch = app.state.orchestrator

    before = await orch.aget_state(cfg)
    waiting = bool(before.next)  # interrupt 대기 여부는 next 로 판정
    print(f"\n[EVENT] '{req.event}'  (interrupt 대기중={waiting}) → resume 안 함, history append")

    # resume 없이 history 에만 이벤트를 추가 → interrupt 보존
    await orch.aupdate_state(
        cfg, {"messages": [HumanMessage(content=f"[단말이벤트] {req.event}")]}
    )

    after = await orch.aget_state(cfg)
    print(f"[EVENT] next={after.next} (interrupt 유지)  history={len(after.values.get('messages', []))}개")
    return {
        "thread_id": req.thread_id,
        "interrupt_preserved": bool(after.next),
        "history_len": len(after.values.get("messages", [])),
    }


@app.get("/history/{thread_id}")
async def get_history(thread_id: str):
    """checkpoint 에 저장된 대화 히스토리를 그대로 보여준다(검증용)."""
    cfg = {"configurable": {"thread_id": thread_id}}
    snap = await app.state.orchestrator.aget_state(cfg)
    msgs = snap.values.get("messages", [])
    return {
        "thread_id": thread_id,
        "interrupt_waiting": bool(snap.next),  # interrupt 대기 중인지
        "count": len(msgs),
        "messages": [
            {"type": type(m).__name__, "content": m.content} for m in msgs
        ],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
