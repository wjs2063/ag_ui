"""대화형 /chat 클라이언트.

서버 띄우기:
    uv run python -m pocs.interrupt_pattern.main
    # 또는
    uv run uvicorn pocs.interrupt_pattern.main:app --port 8000

다른 셸에서 실행:
    uv run python -m pocs.interrupt_pattern.example_client

사용 방법:
- 매 턴 프롬프트에 보낼 message 를 직접 입력
  * JSON 으로 시작하면 ({, [) 파싱해서 dict / list 로 전송
  * 그 외에는 str 로 전송
- thread_id 는 자동 유지 (첫 응답에서 받아서 다음 요청에 자동 첨부)
- 명령어:
    /new   현재 thread_id 폐기 후 새 대화 시작
    /raw   다음 입력을 JSON 파싱 없이 무조건 str 로 보냄
    /show  현재 thread_id 확인
    /quit  종료
- 응답에 done=true 가 오면 자동으로 새 thread 로 리셋
"""

import asyncio
import json
from typing import Any

import httpx

BASE_URL = "http://127.0.0.1:8000"


def parse_user_input(raw: str) -> Any:
    s = raw.strip()
    if s.startswith(("{", "[")):
        try:
            return json.loads(s)
        except json.JSONDecodeError as e:
            print(f"  ! JSON 파싱 실패 ({e}). str 로 전송합니다.")
            return raw
    return raw


async def send_turn(
    client: httpx.AsyncClient, thread_id: str | None, message: Any
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
    print("입력 예) hi  /  재현  /  {\"choice\":\"yes\"}  /  {\"action\":\"approve\"}")
    print("명령어 ) /new  /raw  /show  /quit\n")

    thread_id: str | None = None
    force_str_next = False

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        turn = 1
        while True:
            tag = f"turn {turn} (thread_id={thread_id or '∅'})"
            try:
                raw = input(f"\n[{tag}] message> ")
            except (EOFError, KeyboardInterrupt):
                print("\nbye")
                return

            if not raw.strip():
                continue
            if raw.strip() == "/quit":
                print("bye")
                return
            if raw.strip() == "/new":
                thread_id = None
                turn = 1
                print("  (thread_id 초기화)")
                continue
            if raw.strip() == "/show":
                print(f"  thread_id = {thread_id!r}")
                continue
            if raw.strip() == "/raw":
                force_str_next = True
                print("  (다음 입력은 str 로 전송)")
                continue

            message: Any = raw if force_str_next else parse_user_input(raw)
            force_str_next = False
            print(f"  · parsed type = {type(message).__name__}")

            data = await send_turn(client, thread_id, message)
            if not data:
                continue

            if "thread_id" in data:
                thread_id = data["thread_id"]
            if data.get("done") is True:
                print(f"  ✓ 대화 종료 — 다음 입력은 새 thread 로 시작합니다.")
                thread_id = None
                turn = 1
            else:
                turn += 1


if __name__ == "__main__":
    asyncio.run(main())
