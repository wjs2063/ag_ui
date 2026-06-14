"""Simple A2A client wrappers used by tests and manual smoke runs."""

import json
import uuid
from typing import Any

import httpx
from a2a.client import A2ACardResolver
from a2a.client.legacy import A2AClient
from a2a.types import (
    DataPart,
    Message,
    MessageSendParams,
    Part,
    Role,
    SendMessageRequest,
    TextPart,
)
from langchain_core.messages import BaseMessage, messages_to_dict


def _text_message(text: str, *, task_id: str | None, context_id: str | None) -> Message:
    return Message(
        message_id=str(uuid.uuid4()),
        role=Role.user,
        parts=[Part(TextPart(text=text))],
        task_id=task_id,
        context_id=context_id,
    )


def _data_message(
    question: str,
    history: list[BaseMessage],
    *,
    task_id: str | None,
    context_id: str | None,
) -> Message:
    """DataPart 로 요청. data=현재 질문, metadata.history=직렬화된 대화 히스토리."""
    part = Part(
        DataPart(
            data={"question": question},
            metadata={"history": messages_to_dict(history)},
        )
    )
    return Message(
        message_id=str(uuid.uuid4()),
        role=Role.user,
        parts=[part],
        task_id=task_id,
        context_id=context_id,
    )


async def get_agent_card(httpx_client: httpx.AsyncClient, base_url: str):
    resolver = A2ACardResolver(httpx_client=httpx_client, base_url=base_url)
    return await resolver.get_agent_card()


async def send_text(
    httpx_client: httpx.AsyncClient,
    base_url: str,
    text: str,
    *,
    task_id: str | None = None,
    context_id: str | None = None,
) -> dict[str, Any]:
    card = await get_agent_card(httpx_client, base_url)
    client = A2AClient(httpx_client=httpx_client, agent_card=card)
    msg = _text_message(text, task_id=task_id, context_id=context_id)
    request = SendMessageRequest(
        id=str(uuid.uuid4()),
        params=MessageSendParams(message=msg),
    )
    response = await client.send_message(request)
    return response.model_dump(mode="python", exclude_none=True)


async def ask_agent(
    httpx_client: httpx.AsyncClient,
    base_url: str,
    question: str,
    history: list[BaseMessage],
    *,
    task_id: str | None = None,
    context_id: str | None = None,
) -> tuple[str, str, str]:
    """A2A 에이전트에 DataPart(question + history) 로 보내고 (상태, 응답텍스트, task_id) 반환."""
    card = await get_agent_card(httpx_client, base_url)
    client = A2AClient(httpx_client=httpx_client, agent_card=card)
    msg = _data_message(question, history, task_id=task_id, context_id=context_id)
    request = SendMessageRequest(
        id=str(uuid.uuid4()),
        params=MessageSendParams(message=msg),
    )
    print(f"[서버 → A2A] DataPart question={question!r}  history={len(history)}개")
    response = await client.send_message(request)
    resp = response.model_dump(mode="python", exclude_none=True)

    # A2A 원본 응답 전체(Task, status, state, history 등)를 그대로 출력
    print("┌───── A2A 원본 응답 (raw) ─────")
    print(json.dumps(resp, ensure_ascii=False, indent=2, default=str))
    print("└──────────────────────────────")

    if "result" not in resp:  # A2A 가 JSON-RPC 에러를 반환한 경우
        raise RuntimeError(f"A2A 응답 오류: {resp.get('error')}")
    result = resp["result"]
    status = result["status"]
    print(
        f"[A2A] kind={result.get('kind')} task_id={result.get('id')} "
        f"state={status['state']} timestamp={status.get('timestamp')}"
    )
    print(f"[A2A] history 길이={len(result.get('history') or [])}")
    parts = status["message"]["parts"]
    reply = next(p["text"] for p in parts if p.get("kind") == "text")
    return status["state"], reply, result["id"]
