from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import StateGraph, START, END

from pocs.interrupt_pattern.nodes import (
    ask_and_respond,
    call_external_agent,
    route_after_agent,
    user_turn,
)
from pocs.interrupt_pattern.state import ChatState, OrchestratorState


def build_graph(checkpointer: BaseCheckpointSaver):
    g = StateGraph(ChatState)
    g.add_node("ask_and_respond", ask_and_respond)
    g.add_edge(START, "ask_and_respond")
    g.add_edge("ask_and_respond", END)
    return g.compile(checkpointer=checkpointer)


def build_orchestrator_graph(checkpointer: BaseCheckpointSaver):
    # 대화 thread 는 절대 끝나지 않음: 외부 호출 → (상태 무관) user_turn 에서 응답 대기 → 반복
    g = StateGraph(OrchestratorState)
    g.add_node("call_external_agent", call_external_agent)
    g.add_node("user_turn", user_turn)
    g.add_edge(START, "call_external_agent")
    g.add_conditional_edges(
        "call_external_agent",
        route_after_agent,
        {"user_turn": "user_turn"},
    )
    g.add_edge("user_turn", "call_external_agent")
    return g.compile(checkpointer=checkpointer)
