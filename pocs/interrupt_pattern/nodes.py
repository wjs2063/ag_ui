import json

import httpx
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from pocs.interrupt_pattern.a2a_client.client import ask_agent
from pocs.interrupt_pattern.config import A2A_HOST, A2A_PORT
from pocs.interrupt_pattern.state import ChatState, OrchestratorState

EXTERNAL_A2A_URL = f"http://{A2A_HOST}:{A2A_PORT}/"


def print_history(messages: list) -> None:
    """현재까지 누적된 전체 대화 히스토리를 출력한다(매 턴 확인용)."""
    print(f"===== HISTORY ({len(messages)}개) =====")
    for i, m in enumerate(messages, 1):
        role = "User" if isinstance(m, HumanMessage) else "AI  "
        print(f"  {i:2}. [{role}] {m.content}")
    print("=" * 30)


def _question(text: str) -> str:
    """{"question","metadata"} 또는 {"type","question"} JSON 에서 question 만 뽑는다."""
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data.get("question") or text
    except (json.JSONDecodeError, TypeError):
        pass
    return text


def ask_and_respond(state: ChatState) -> dict:
    payload = interrupt({"type": "ask_name", "question": "이름을 알려주세요"})
    print("ask_and_respond node :", payload, type(payload).__name__)
    name = (payload or {}).get("name", "")
    return {
        "name": name,
        "response": {"type": "greeting", "text": f"안녕하세요, {name}님!"},
    }


async def call_external_agent(
    state: OrchestratorState, config: RunnableConfig
) -> dict:
    """외부 A2A 에이전트를 1회 호출. (interrupt 는 user_turn 에서만 건다.)"""
    thread_id = config["configurable"]["thread_id"]
    msgs = state.get("messages", [])
    history = msgs[:-1]  # 직전까지의 대화 맥락(현재 질문 제외)
    question = msgs[-1].content if msgs else ""  # 현재 사용자 질문(턴1 킥오프는 빈값)
    async with httpx.AsyncClient(timeout=30) as client:
        # DataPart(question + history) 로 요청. A2A 는 history+question 으로 맥락 답변
        a2a_state, reply, _ = await ask_agent(
            client, EXTERNAL_A2A_URL, question, history, context_id=f"a2a-{thread_id}"
        )
    print(f"[A2A → 서버]   state={a2a_state}  reply={reply}")

    # Agent 응답을 AIMessage 로 히스토리에 누적
    ai = AIMessage(content=_question(reply))
    print_history(list(msgs) + [ai])  # 이번 턴 반영된 전체 히스토리
    return {
        "reply": reply,
        "input_required": a2a_state == "input-required",
        "messages": [ai],
    }


def route_after_agent(state: OrchestratorState) -> str:
    """대화 thread 는 절대 끝나지 않는다 → 어떤 상태든 user_turn 에서 응답을 대기.

    input_required: 같은 흐름을 이어서 대기.
    completed(그 외): 주제는 끝났지만 END 로 가지 않고, 같은 thread 로 다음 입력을 대기.
    """
    if state.get("input_required"):
        print("[ROUTE] input_required → user_turn (이어서 대기)")
    else:
        print("[ROUTE] completed → user_turn (주제 종료, 같은 thread 로 새 입력 대기)")
    return "user_turn"


def user_turn(state: OrchestratorState) -> dict:
    """영구 대화: A2A 응답을 클라이언트에 건네고(interrupt) 다음 입력을 기다린다.

    interrupt 로 멈췄다가 사용자가 응답하면 그 입력을 HumanMessage 로 누적한다.
    outgoing/reply 채널을 분리해야 interrupt resume 매칭이 꼬이지 않는다.
    """
    answer = interrupt(state.get("reply"))
    question = answer.get("question", "") if isinstance(answer, dict) else str(answer)
    human = HumanMessage(content=question)
    total = len(state.get("messages", [])) + 1
    print(f"[HISTORY] + HumanMessage : {human.content!r}  → 총 {total}개")
    return {"messages": [human]}
