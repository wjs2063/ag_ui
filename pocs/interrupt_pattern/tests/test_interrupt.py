import pytest


pytestmark = pytest.mark.asyncio


async def _post(client, thread_id: str | None, message):
    body = {"message": message}
    if thread_id is not None:
        body["thread_id"] = thread_id
    r = await client.post("/chat", json=body)
    return r


async def test_first_message_returns_str_question(fastapi_client, thread_id):
    r = await _post(fastapi_client, thread_id, "hi")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["thread_id"] == thread_id
    assert body["done"] is False
    assert body["message"] == "이름을 알려주세요"


async def test_next_message_returns_confirm_dict(fastapi_client, thread_id):
    await _post(fastapi_client, thread_id, "hi")
    r = await _post(fastapi_client, thread_id, "재현")
    body = r.json()
    assert body["done"] is False
    assert isinstance(body["message"], dict)
    assert body["message"]["type"] == "confirm"
    assert "재현" in body["message"]["question"]
    assert body["message"]["options"] == ["yes", "no"]


async def test_next_message_returns_tool_review_dict(fastapi_client, thread_id):
    await _post(fastapi_client, thread_id, "hi")
    await _post(fastapi_client, thread_id, "재현")
    r = await _post(fastapi_client, thread_id, {"choice": "yes"})
    body = r.json()
    assert body["done"] is False
    payload = body["message"]
    assert isinstance(payload, dict)
    assert payload["tool"] == "send_email"
    assert payload["args"]["to"].startswith("재현")
    assert payload["reason"]


async def test_invalid_tool_review_reprompts_without_breaking_thread(
    fastapi_client, thread_id
):
    await _post(fastapi_client, thread_id, "hi")
    await _post(fastapi_client, thread_id, "재현")
    await _post(fastapi_client, thread_id, {"choice": "yes"})
    # 잘못된 모양 → 422 가 아니라 같은 노드에서 다시 묻는 interrupt 가 와야 함
    r = await _post(fastapi_client, thread_id, {"note": "bad"})
    body = r.json()
    assert r.status_code == 200, r.text
    assert body["done"] is False
    assert "last_error" in body["message"]
    # 같은 thread 에서 올바른 값으로 재시도 → 정상 완료
    r2 = await _post(
        fastapi_client, thread_id, {"action": "approve", "note": "retry"}
    )
    body2 = r2.json()
    assert body2["done"] is True
    assert "approve" in body2["message"]


async def test_invalid_confirm_reprompts_without_breaking_thread(
    fastapi_client, thread_id
):
    await _post(fastapi_client, thread_id, "hi")
    await _post(fastapi_client, thread_id, "재현")
    # 오타: chioice
    r = await _post(fastapi_client, thread_id, {"chioice": "yes"})
    body = r.json()
    assert r.status_code == 200
    assert body["done"] is False
    assert body["message"]["last_error"]
    # 올바른 값으로 재시도 → 정상 진행
    r2 = await _post(fastapi_client, thread_id, {"choice": "yes"})
    body2 = r2.json()
    assert body2["done"] is False
    assert body2["message"]["type"] == "tool_review"


async def test_full_chat_completes_with_done_true(fastapi_client, thread_id):
    await _post(fastapi_client, thread_id, "hi")
    await _post(fastapi_client, thread_id, "재현")
    await _post(fastapi_client, thread_id, {"choice": "yes"})
    r = await _post(fastapi_client, thread_id, {"action": "approve", "note": "OK"})
    body = r.json()
    assert body["done"] is True
    assert isinstance(body["message"], str)
    assert "재현" in body["message"]
    assert "approve" in body["message"]


async def test_state_endpoint(fastapi_client, thread_id):
    await _post(fastapi_client, thread_id, "hi")
    r = await fastapi_client.get(f"/state/{thread_id}")
    body = r.json()
    assert body["thread_id"] == thread_id
    assert body["awaiting_input"] is True


async def test_new_thread_when_thread_id_omitted(fastapi_client):
    r1 = await fastapi_client.post("/chat", json={"message": "hi"})
    r2 = await fastapi_client.post("/chat", json={"message": "hi"})
    assert r1.json()["thread_id"] != r2.json()["thread_id"]
    assert r1.json()["message"] == r2.json()["message"] == "이름을 알려주세요"
