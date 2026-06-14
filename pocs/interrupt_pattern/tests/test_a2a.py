import json
import uuid

import pytest

from pocs.interrupt_pattern.a2a_client.client import get_agent_card, send_text


pytestmark = pytest.mark.asyncio


def _result(resp):
    return resp["result"]


def _state(resp):
    return _result(resp)["status"]["state"]


def _agent_text(resp):
    return next(
        p["text"]
        for p in _result(resp)["status"]["message"]["parts"]
        if p.get("kind") == "text"
    )


async def test_agent_card_discovery(a2a_client_setup):
    card = await get_agent_card(a2a_client_setup, "http://test")
    assert card.name == "Interrupt Pattern Agent"
    assert card.skills


async def test_a2a_first_call_triggers_interrupt(a2a_client_setup):
    ctx = f"ctx-{uuid.uuid4().hex[:8]}"
    resp = await send_text(a2a_client_setup, "http://test", "{}", context_id=ctx)
    assert _state(resp) == "input-required"
    payload = json.loads(_agent_text(resp))
    assert payload == {"type": "ask_name", "question": "이름을 알려주세요"}


async def test_a2a_resume_completes(a2a_client_setup):
    ctx = f"ctx-{uuid.uuid4().hex[:8]}"

    r1 = await send_text(a2a_client_setup, "http://test", "{}", context_id=ctx)
    server_task_id = _result(r1)["id"]

    r2 = await send_text(
        a2a_client_setup,
        "http://test",
        '{"name": "재현"}',
        task_id=server_task_id,
        context_id=ctx,
    )
    assert _state(r2) == "completed"
    payload = json.loads(_agent_text(r2))
    assert payload == {"type": "greeting", "text": "안녕하세요, 재현님!"}
