"""astream_events 원본 이벤트 vs AG-UI 변환 이벤트를 나란히 확인하는 스크립트

Redis/OpenAI 없이 동작하도록 Fake LLM + MemorySaver 사용
"""

import asyncio
import operator
import json
from typing import Annotated

from langchain_core.messages import AIMessageChunk
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from typing_extensions import TypedDict

# AG-UI
from ag_ui.core import (
    RunStartedEvent,
    RunFinishedEvent,
    StepStartedEvent,
    StepFinishedEvent,
    TextMessageStartEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    CustomEvent,
)
from ag_ui.encoder import EventEncoder

encoder = EventEncoder()

STREAMING_NODE = "summarize"


# ── Fake LLM (토큰 단위로 스트리밍 시뮬레이션) ──
fake_llm = FakeListChatModel(
    responses=[
        "리서치 결과: AI는 빠르게 발전하고 있습니다.",        # research 노드
        "분석 결과: AI 발전 속도가 가속화되고 있습니다.",      # analyze 노드
        "요약: AI는 모든 산업을 변화시키고 있습니다.",          # summarize display
        "AI가 세상을 바꾸고 있어요. 정말 빠르게요.",            # summarize tts
    ]
)


# ── State & Graph ──
class TestState(TypedDict):
    query: str
    messages: Annotated[list, operator.add]
    research_result: str
    analysis_result: str
    display_text: str
    tts_text: str
    current_step: str


async def research(state: TestState) -> dict:
    response = await fake_llm.ainvoke(f"리서치: {state['query']}")
    return {
        "research_result": response.content,
        "current_step": "research",
        "messages": [{"role": "assistant", "content": "[리서치 완료]"}],
    }


async def analyze(state: TestState) -> dict:
    response = await fake_llm.ainvoke(f"분석: {state['research_result']}")
    return {
        "analysis_result": response.content,
        "current_step": "analyze",
        "messages": [{"role": "assistant", "content": "[분석 완료]"}],
    }


async def summarize(state: TestState) -> dict:
    display_task = fake_llm.ainvoke(
        f"요약: {state['analysis_result']}",
        config={"tags": ["display"]},
    )
    tts_task = fake_llm.ainvoke(
        f"TTS: {state['analysis_result']}",
        config={"tags": ["tts"]},
    )
    display_resp, tts_resp = await asyncio.gather(display_task, tts_task)
    return {
        "display_text": display_resp.content,
        "tts_text": tts_resp.content,
        "current_step": "summarize",
        "messages": [{"role": "assistant", "content": display_resp.content}],
    }


def build_test_graph():
    graph = StateGraph(TestState)
    graph.add_node("research", research)
    graph.add_node("analyze", analyze)
    graph.add_node("summarize", summarize)
    graph.add_edge(START, "research")
    graph.add_edge("research", "analyze")
    graph.add_edge("analyze", "summarize")
    graph.add_edge("summarize", END)
    return graph.compile(checkpointer=MemorySaver())


SEPARATOR = "=" * 80


async def part1_raw_events():
    """Part 1: astream_events 원본 이벤트"""
    print(f"\n{SEPARATOR}")
    print("📦 Part 1: graph.astream_events() 원본 이벤트")
    print(f"{SEPARATOR}\n")

    workflow = build_test_graph()
    config = {"configurable": {"thread_id": "test-1"}}
    initial = {
        "query": "AI 트렌드",
        "messages": [],
        "research_result": "",
        "analysis_result": "",
        "display_text": "",
        "tts_text": "",
        "current_step": "",
    }

    count = 0
    async for event in workflow.astream_events(initial, config=config, version="v2"):
        count += 1
        kind = event["event"]
        name = event.get("name", "")
        tags = event.get("tags", [])

        # 주요 이벤트만 출력 (너무 많은 내부 이벤트 필터링)
        if kind in ("on_chain_start", "on_chain_end", "on_chat_model_start",
                     "on_chat_model_end", "on_chat_model_stream"):

            print(f"[{count:03d}] event: {kind}")
            print(f"      name:  {name}")
            if tags:
                print(f"      tags:  {tags}")

            data = event.get("data", {})
            if kind == "on_chat_model_stream":
                chunk = data.get("chunk")
                if chunk and hasattr(chunk, "content"):
                    print(f"      chunk: \"{chunk.content}\"")
            elif kind == "on_chain_end":
                output = data.get("output", {})
                if isinstance(output, dict):
                    # messages 제외하고 출력
                    filtered = {k: v for k, v in output.items()
                                if k != "messages" and v}
                    if filtered:
                        print(f"      output: {json.dumps(filtered, ensure_ascii=False, indent=8)}")
            print()

    print(f"총 {count}개 이벤트 발생")


async def part2_agui_events():
    """Part 2: AG-UI SSE로 변환된 이벤트"""
    print(f"\n{SEPARATOR}")
    print("🖥️  Part 2: AG-UI SSE 변환 결과 (프론트엔드가 받는 것)")
    print(f"{SEPARATOR}\n")

    workflow = build_test_graph()
    config = {"configurable": {"thread_id": "test-2"}}
    initial = {
        "query": "AI 트렌드",
        "messages": [],
        "research_result": "",
        "analysis_result": "",
        "display_text": "",
        "tts_text": "",
        "current_step": "",
    }

    current_node = None
    msg_id = "msg-001"
    event_num = 0

    def emit(label: str, event):
        nonlocal event_num
        event_num += 1
        sse = encoder.encode(event).strip()
        print(f"[{event_num:03d}] {label}")
        print(f"      SSE → {sse}")
        print()

    emit("RUN_STARTED", RunStartedEvent(thread_id="thread-1", run_id="run-1"))

    async for event in workflow.astream_events(initial, config=config, version="v2"):
        kind = event["event"]
        name = event.get("name", "")

        # 노드 시작
        if kind == "on_chain_start" and name in ("research", "analyze", STREAMING_NODE):
            current_node = name
            emit(f"STEP_STARTED ({name})", StepStartedEvent(step_name=name))

            if name == STREAMING_NODE:
                emit("TEXT_MESSAGE_START", TextMessageStartEvent(
                    message_id=msg_id, role="assistant"
                ))

        # LLM 토큰 (display 태그만)
        if (kind == "on_chat_model_stream"
                and current_node == STREAMING_NODE
                and "display" in event.get("tags", [])):
            chunk = event["data"]["chunk"]
            if hasattr(chunk, "content") and chunk.content:
                emit(
                    f"TEXT_MESSAGE_CONTENT (delta: \"{chunk.content}\")",
                    TextMessageContentEvent(message_id=msg_id, delta=chunk.content)
                )

        # 노드 종료
        if kind == "on_chain_end" and name in ("research", "analyze", STREAMING_NODE):
            if name == STREAMING_NODE:
                emit("TEXT_MESSAGE_END", TextMessageEndEvent(message_id=msg_id))

                output = event.get("data", {}).get("output", {})
                tts = output.get("tts_text", "")
                if tts:
                    emit(
                        f"CUSTOM tts_text: \"{tts}\"",
                        CustomEvent(name="tts_text", value=tts)
                    )

            emit(f"STEP_FINISHED ({name})", StepFinishedEvent(step_name=name))
            current_node = None

    emit("RUN_FINISHED", RunFinishedEvent(thread_id="thread-1", run_id="run-1"))


async def main():
    await part1_raw_events()
    await part2_agui_events()


if __name__ == "__main__":
    asyncio.run(main())
