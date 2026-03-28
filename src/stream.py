"""LangGraph astream_events → AG-UI SSE 이벤트 변환

스트리밍 전략:
- 중간 노드: STEP_STARTED/FINISHED만 (진행률 표시)
- 마지막 노드: 2개 LLM 동시 호출 (asyncio.gather)
  - tag="display" → TEXT_MESSAGE_CONTENT로 토큰 실시간 스트리밍
  - tag="tts"     → 무시, 노드 완료 시 CUSTOM 이벤트로 한번에 전달
"""

import uuid
from collections.abc import AsyncGenerator

from ag_ui.core import (
    RunStartedEvent,
    RunFinishedEvent,
    RunErrorEvent,
    StepStartedEvent,
    StepFinishedEvent,
    TextMessageStartEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    StateSnapshotEvent,
    CustomEvent,
)
from ag_ui.encoder import EventEncoder

from src.graph import get_workflow, WorkflowState, STREAMING_NODE

encoder = EventEncoder()


def _sse(event) -> str:
    return encoder.encode(event)


def _has_tag(event: dict, tag: str) -> bool:
    return tag in event.get("tags", [])


async def run_workflow_stream(
    query: str,
    thread_id: str | None = None,
) -> AsyncGenerator[str, None]:
    thread_id = thread_id or str(uuid.uuid4())
    run_id = str(uuid.uuid4())

    yield _sse(RunStartedEvent(thread_id=thread_id, run_id=run_id))

    config = {"configurable": {"thread_id": thread_id}}
    initial_state: WorkflowState = {
        "query": query,
        "messages": [],
        "research_result": "",
        "analysis_result": "",
        "display_text": "",
        "tts_text": "",
        "current_step": "",
    }

    current_node = None
    msg_id = None

    try:
        async for event in get_workflow().astream_events(
            initial_state, config=config, version="v2"
        ):
            kind = event["event"]
            name = event.get("name", "")

            # ── 노드 시작 ──
            if kind == "on_chain_start" and name in ("research", "analyze", STREAMING_NODE):
                current_node = name
                yield _sse(StepStartedEvent(step_name=current_node))

                if current_node == STREAMING_NODE:
                    msg_id = str(uuid.uuid4())
                    yield _sse(
                        TextMessageStartEvent(message_id=msg_id, role="assistant")
                    )

            # ── LLM 토큰 스트리밍 (display 태그만) ──
            if (
                kind == "on_chat_model_stream"
                and current_node == STREAMING_NODE
                and _has_tag(event, "display")
            ):
                chunk = event["data"]["chunk"]
                if hasattr(chunk, "content") and chunk.content:
                    yield _sse(
                        TextMessageContentEvent(message_id=msg_id, delta=chunk.content)
                    )
            # tts 태그 토큰은 무시 (노드 output에서 한번에 가져감)

            # ── 노드 종료 ──
            if kind == "on_chain_end" and name in ("research", "analyze", STREAMING_NODE):
                if name == STREAMING_NODE:
                    if msg_id:
                        yield _sse(TextMessageEndEvent(message_id=msg_id))

                    # tts_text: 노드 output에서 완성된 텍스트를 한번에 전달
                    output = event.get("data", {}).get("output", {})
                    tts_text = output.get("tts_text", "")
                    if tts_text:
                        yield _sse(CustomEvent(name="tts_text", value=tts_text))

                yield _sse(StepFinishedEvent(step_name=name))

                output = event.get("data", {}).get("output", {})
                if output:
                    yield _sse(
                        StateSnapshotEvent(
                            snapshot={
                                "current_step": name,
                                **{k: v for k, v in output.items() if k != "messages"},
                            }
                        )
                    )

                current_node = None
                msg_id = None

        yield _sse(RunFinishedEvent(thread_id=thread_id, run_id=run_id))

    except Exception as e:
        yield _sse(
            RunErrorEvent(thread_id=thread_id, run_id=run_id, message=str(e))
        )
