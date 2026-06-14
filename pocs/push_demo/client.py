"""긴 작업을 요청하고 webhook 을 등록한 뒤 즉시 반환받는 클라이언트.

실행:  uv run python -m pocs.push_demo.client
(agent, webhook 서버가 먼저 떠 있어야 함)
"""

import asyncio
import uuid

import httpx
from a2a.client import A2ACardResolver
from a2a.client.legacy import A2AClient
from a2a.types import (
    Message,
    MessageSendConfiguration,
    MessageSendParams,
    Part,
    PushNotificationConfig,
    Role,
    SendMessageRequest,
    TextPart,
)

AGENT = "http://127.0.0.1:9101"
WEBHOOK = "http://127.0.0.1:9102/"


async def main():
    async with httpx.AsyncClient(timeout=30) as hc:
        card = await A2ACardResolver(httpx_client=hc, base_url=AGENT).get_agent_card()
        client = A2AClient(httpx_client=hc, agent_card=card)

        req = SendMessageRequest(
            id=str(uuid.uuid4()),
            params=MessageSendParams(
                message=Message(
                    message_id=str(uuid.uuid4()),
                    role=Role.user,
                    parts=[Part(TextPart(text="긴 작업 해줘"))],
                ),
                configuration=MessageSendConfiguration(
                    blocking=False,  # 즉시 반환(작업은 백그라운드)
                    push_notification_config=PushNotificationConfig(url=WEBHOOK),  # webhook 등록
                ),
            ),
        )
        resp = await client.send_message(req)
        result = resp.model_dump(mode="python", exclude_none=True).get("result", {})
        print("즉시 응답 state:", (result.get("status") or {}).get("state"), "| task:", result.get("id"))
        print("→ 작업이 끝나면 webhook 터미널로 완료 push 가 도착합니다.")


if __name__ == "__main__":
    asyncio.run(main())
