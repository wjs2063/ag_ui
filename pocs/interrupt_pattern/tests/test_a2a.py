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
    assert card.skills[0].id == "interrupt_chat"


async def test_a2a_roundtrip_first_interrupt(a2a_client_setup):
    context_id = f"ctx-{uuid.uuid4().hex[:8]}"
    resp = await send_text(
        a2a_client_setup, "http://test", "hi", context_id=context_id
    )
    assert _state(resp) == "input-required"
    assert _agent_text(resp) == "이름을 알려주세요"


async def test_a2a_resume_via_followup_message(a2a_client_setup):
    context_id = f"ctx-{uuid.uuid4().hex[:8]}"

    r1 = await send_text(
        a2a_client_setup, "http://test", "hi", context_id=context_id
    )
    assert _state(r1) == "input-required"
    server_task_id = _result(r1)["id"]

    r2 = await send_text(
        a2a_client_setup,
        "http://test",
        "재현",
        task_id=server_task_id,
        context_id=context_id,
    )
    assert _state(r2) == "input-required"
    assert "재현" in _agent_text(r2) and "계속" in _agent_text(r2)


async def test_a2a_full_chain_to_completion(a2a_client_setup):
    context_id = f"ctx-{uuid.uuid4().hex[:8]}"

    r1 = await send_text(
        a2a_client_setup, "http://test", "hi", context_id=context_id
    )
    server_task_id = _result(r1)["id"]

    await send_text(
        a2a_client_setup,
        "http://test",
        "재현",
        task_id=server_task_id,
        context_id=context_id,
    )
    await send_text(
        a2a_client_setup,
        "http://test",
        '{"choice": "yes"}',
        task_id=server_task_id,
        context_id=context_id,
    )
    r4 = await send_text(
        a2a_client_setup,
        "http://test",
        '{"action": "approve", "note": "from A2A"}',
        task_id=server_task_id,
        context_id=context_id,
    )
    assert _state(r4) == "completed"
    text = _agent_text(r4)
    assert "재현" in text and "approve" in text
