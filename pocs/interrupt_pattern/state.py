from typing import Annotated, Any

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class ChatState(TypedDict, total=False):
    name: str
    response: dict[str, Any]


class OrchestratorState(TypedDict, total=False):
    reply: str  # A2A → 클라이언트 응답(질문). interrupt 로 사용자에게 전달
    input_required: bool  # A2A TaskStatus 가 input_required 인지 (interrupt 분기용)
    messages: Annotated[list[AnyMessage], add_messages]  # checkpoint 에 누적되는 대화 히스토리
