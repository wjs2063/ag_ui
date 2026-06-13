from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import StateGraph, START, END

from pocs.interrupt_pattern.nodes import ask_name, confirm, tool_review, respond
from pocs.interrupt_pattern.state import ChatState


def build_graph(checkpointer: BaseCheckpointSaver):
    g = StateGraph(ChatState)
    g.add_node("ask_name", ask_name)
    g.add_node("confirm", confirm)
    g.add_node("tool_review", tool_review)
    g.add_node("respond", respond)

    g.add_edge(START, "ask_name")
    g.add_edge("ask_name", "confirm")
    g.add_edge("confirm", "tool_review")
    g.add_edge("tool_review", "respond")
    g.add_edge("respond", END)

    return g.compile(checkpointer=checkpointer)
