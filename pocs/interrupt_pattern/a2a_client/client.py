"""Simple A2A client wrappers used by tests and manual smoke runs."""

import uuid
from typing import Any

import httpx
from a2a.client import A2ACardResolver
from a2a.client.legacy import A2AClient
from a2a.types import (
    Message,
    MessageSendParams,
    Part,
    Role,
    SendMessageRequest,
    TextPart,
)


def _text_message(text: str, *, task_id: str | None, context_id: str | None) -> Message:
    return Message(
        message_id=str(uuid.uuid4()),
        role=Role.user,
        parts=[Part(TextPart(text=text))],
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
