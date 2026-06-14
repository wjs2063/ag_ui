"""대화형 /chat 클라이언트.

서버 띄우기:
    uv run python -m pocs.interrupt_pattern.main
    # 또는
    uv run uvicorn pocs.interrupt_pattern.main:app --port 8000

다른 셸에서 실행:
    uv run python -m pocs.interrupt_pattern.example_client

사용 방법:
- 매 턴 프롬프트에 보낼 **dict** 를 JSON 으로 직접 입력 (예: {} / {"name":"재현"})
- thread_id 는 자동 유지 (첫 응답에서 받아서 다음 요청에 자동 첨부)
- 명령어:
    /new   현재 thread_id 폐기 후 새 대화 시작
    /show  현재 thread_id 확인
    /quit  종료
- 응답에 done=true 가 오면 자동으로 새 thread 로 리셋
- 서버 계약: message 는 항상 dict (str 보내면 422)
"""

import asyncio
import json
from typing import Any

import httpx

BASE_URL = "http://127.0.0.1:8000"


def parse_dict_input(raw: str) -> dict | None:
    s = raw.strip()
    if not s:
        return {}
    try:
        data = json.loads(s)
    except json.JSONDecodeError as e:
        print(f"  ! JSON 파싱 실패: {e}")
        return None
    if not isinstance(data, dict):
        print(f"  ! dict 가 아닙니다 (got {type(data).__name__}). 다시 입력하세요.")
        return None
    return data


async def send_turn(
    client: httpx.AsyncClient, thread_id: str | None, message: dict
) -> dict:
    body: dict[str, Any] = {"message": message}
    if thread_id is not None:
        body["thread_id"] = thread_id
    print("  ▶ REQUEST :", json.dumps(body, ensure_ascii=False))
    r = await client.post("/chat", json=body)
    print(f"  ◀ STATUS  : {r.status_code}")
    try:
        data = r.json()
    except Exception:
        print("  ◀ BODY    :", r.text)
        return {}
    print("  ◀ RESPONSE:", json.dumps(data, ensure_ascii=False))
    return data


async def main() -> None:
    print(f"== interrupt_pattern interactive client → {BASE_URL} ==")
    print('입력 예) {}  /  {"name":"재현"}')
    print("명령어 ) /new  /show  /quit\n")

    thread_id: str | None = None

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        turn = 1
        while True:
            tag = f"turn {turn} (thread_id={thread_id or '∅'})"
            try:
                raw = input(f"\n[{tag}] message (dict)> ")
            except (EOFError, KeyboardInterrupt):
                print("\nbye")
                return

            stripped = raw.strip()
            if stripped == "/quit":
                print("bye")
                return
            if stripped == "/new":
                thread_id = None
                turn = 1
                print("  (thread_id 초기화)")
                continue
            if stripped == "/show":
                print(f"  thread_id = {thread_id!r}")
                continue

            message = parse_dict_input(raw)
            if message is None:
                continue
            print(f"  · parsed: {message!r}")

            data = await send_turn(client, thread_id, message)
            if not data or "thread_id" not in data:
                continue

            thread_id = data["thread_id"]
            if data.get("done") is True:
                print("  ✓ 대화 종료 — 다음 입력은 새 thread 로 시작합니다.")
                thread_id = None
                turn = 1
            else:
                turn += 1


if __name__ == "__main__":
    asyncio.run(main())
