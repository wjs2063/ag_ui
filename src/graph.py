"""간단한 LangGraph 워크플로우: 리서치 → 분석 → 요약"""

import asyncio
import operator
from typing import Annotated

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from typing_extensions import TypedDict

from src.checkpoint import get_checkpointer

STREAMING_NODE = "summarize"


class WorkflowState(TypedDict):
    query: str
    messages: Annotated[list, operator.add]
    research_result: str
    analysis_result: str
    display_text: str
    tts_text: str
    current_step: str


def _get_llm():
    return ChatOpenAI(model="gpt-4o-mini", temperature=0)


async def research(state: WorkflowState) -> dict:
    query = state["query"]
    response = await _get_llm().ainvoke(
        f"다음 주제에 대해 핵심 정보를 3가지로 정리해줘: {query}"
    )
    return {
        "research_result": response.content,
        "current_step": "research",
        "messages": [{"role": "assistant", "content": "[리서치 완료]"}],
    }


async def analyze(state: WorkflowState) -> dict:
    research = state["research_result"]
    response = await _get_llm().ainvoke(
        f"다음 리서치 결과를 분석하고 인사이트를 도출해줘:\n{research}"
    )
    return {
        "analysis_result": response.content,
        "current_step": "analyze",
        "messages": [{"role": "assistant", "content": "[분석 완료]"}],
    }


async def summarize(state: WorkflowState) -> dict:
    """display_text와 tts_text를 동시 호출 (asyncio.gather)

    - display: tag="display" → stream.py에서 토큰 스트리밍
    - tts: tag="tts" → stream.py에서 무시, 노드 완료 시 한번에 전달
    """
    analysis = state["analysis_result"]
    llm = _get_llm()

    display_task = llm.ainvoke(
        f"다음 분석 결과를 상세하게 요약해줘:\n{analysis}",
        config={"tags": ["display"]},
    )
    tts_task = llm.ainvoke(
        f"다음 내용을 자연스러운 구어체로 5문장 이내로 요약해줘:\n{analysis}",
        config={"tags": ["tts"]},
    )

    display_resp, tts_resp = await asyncio.gather(display_task, tts_task)

    return {
        "display_text": display_resp.content,
        "tts_text": tts_resp.content,
        "current_step": "summarize",
        "messages": [{"role": "assistant", "content": display_resp.content}],
    }


def build_graph():
    graph = StateGraph(WorkflowState)

    graph.add_node("research", research)
    graph.add_node("analyze", analyze)
    graph.add_node("summarize", summarize)

    graph.add_edge(START, "research")
    graph.add_edge("research", "analyze")
    graph.add_edge("analyze", "summarize")
    graph.add_edge("summarize", END)

    checkpointer = get_checkpointer()
    return graph.compile(checkpointer=checkpointer)


_workflow = None


def get_workflow():
    global _workflow
    if _workflow is None:
        _workflow = build_graph()
    return _workflow
