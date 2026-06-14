import pytest


pytestmark = pytest.mark.asyncio


async def _post(client, thread_id: str | None, message: dict):
    body = {"message": message}
    if thread_id is not None:
        body["thread_id"] = thread_id
    return await client.post("/chat", json=body)


async def test_first_message_triggers_interrupt(fastapi_client, thread_id):
    r = await _post(fastapi_client, thread_id, {})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["thread_id"] == thread_id
    assert body["done"] is False
    assert body["message"] == {"type": "ask_name", "question": "이름을 알려주세요"}


async def test_resume_completes_chat(fastapi_client, thread_id):
    await _post(fastapi_client, thread_id, {})
    r = await _post(fastapi_client, thread_id, {"name": "재현"})
    body = r.json()
    assert body["done"] is True
    assert body["message"] == {"type": "greeting", "text": "안녕하세요, 재현님!"}


async def test_non_dict_message_returns_422(fastapi_client, thread_id):
    r = await fastapi_client.post(
        "/chat", json={"thread_id": thread_id, "message": "hi"}
    )
    assert r.status_code == 422


async def test_state_endpoint_shows_awaiting_input(fastapi_client, thread_id):
    await _post(fastapi_client, thread_id, {})
    r = await fastapi_client.get(f"/state/{thread_id}")
    body = r.json()
    assert body["thread_id"] == thread_id
    assert body["awaiting_input"] is True


async def test_new_thread_when_thread_id_omitted(fastapi_client):
    r1 = await fastapi_client.post("/chat", json={"message": {}})
    r2 = await fastapi_client.post("/chat", json={"message": {}})
    assert r1.json()["thread_id"] != r2.json()["thread_id"]
    assert r1.json()["message"] == r2.json()["message"]
