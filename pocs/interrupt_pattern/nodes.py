from typing import Any, Literal

from langgraph.types import interrupt
from pydantic import BaseModel, ValidationError

from pocs.interrupt_pattern.state import ChatState


class ToolReviewRequest(BaseModel):
    type: Literal["tool_review"] = "tool_review"
    tool: str
    args: dict[str, Any]
    reason: str


class ToolReviewDecision(BaseModel):
    action: Literal["approve", "edit", "reject"]
    args: dict[str, Any] | None = None
    note: str | None = None


def ask_name(state: ChatState) -> dict:
    prompt: Any = "이름을 알려주세요"
    while True:
        name = interrupt(prompt)
        print("ask_name node : ", name, type(name).__name__)
        if isinstance(name, str) and name.strip():
            return {"name": name.strip()}
        prompt = f"비어있지 않은 문자열로 이름을 알려주세요 (받은 값: {name!r})"


def confirm(state: ChatState) -> dict:
    payload: Any = {
        "type": "confirm",
        "question": f"{state['name']}님, 계속 진행할까요?",
        "options": ["yes", "no"],
    }
    while True:
        decision = interrupt(payload)
        print("confirm_node : ", decision, type(decision).__name__)
        if (
            isinstance(decision, dict)
            and decision.get("choice") in ("yes", "no")
        ):
            return {"confirm": decision}
        payload = {
            "type": "confirm",
            "question": "형식이 올바르지 않습니다. {\"choice\": \"yes\"} 또는 {\"choice\": \"no\"} 로 보내주세요.",
            "options": ["yes", "no"],
            "last_error": f"got: {decision!r}",
        }


def tool_review(state: ChatState) -> dict:
    request: Any = ToolReviewRequest(
        tool="send_email",
        args={"to": f"{state['name']}@example.com", "subject": "Hello"},
        reason="사용자 확인 후 발송하기 위한 검토",
    ).model_dump()
    while True:
        raw = interrupt(request)
        print("tool_review node : ", raw, type(raw).__name__)
        try:
            decision = ToolReviewDecision.model_validate(raw)
        except ValidationError as e:
            request = {
                "type": "tool_review",
                "question": "tool_review 응답 형식이 올바르지 않습니다.",
                "expected": {
                    "action": "approve|edit|reject",
                    "args?": "dict",
                    "note?": "str",
                },
                "last_error": str(e),
            }
            continue
        return {"tool_decision": decision.model_dump()}


def respond(state: ChatState) -> dict:
    confirm_choice = state.get("confirm", {}).get("choice", "?")
    decision = state.get("tool_decision", {})
    note = decision.get("note")
    text = (
        f"{state['name']}님, 진행 의사: {confirm_choice}. "
        f"도구 검토: {decision.get('action', '?')}"
        + (f" (note: {note})" if note else "")
    )
    return {"response": text}
