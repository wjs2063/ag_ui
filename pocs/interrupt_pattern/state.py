from typing import Annotated, Any
import operator
from typing_extensions import TypedDict


class ChatState(TypedDict, total=False):
    message: str
    name: str
    confirm: dict[str, Any]
    tool_decision: dict[str, Any]
    response: str
    messages: Annotated[list, operator.add]
