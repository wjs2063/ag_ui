"""긴 작업 후 A2A push notification 을 보내는 데모 에이전트 (port 9101).

실행:  uv run python -m pocs.push_demo.agent
"""

import asyncio

import httpx
import uvicorn
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps.jsonrpc.starlette_app import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import (
    BasePushNotificationSender,
    InMemoryPushNotificationConfigStore,
    InMemoryTaskStore,
    TaskUpdater,
)
from a2a.types import AgentCapabilities, AgentCard, AgentSkill, TaskState
from a2a.utils.message import new_agent_text_message


class LongTaskExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id or context.message.message_id
        context_id = context.context_id or task_id
        updater = TaskUpdater(event_queue, task_id, context_id)

        if not context.current_task:
            await updater.submit()
        await updater.start_work()  # working → 클라이언트엔 즉시 이 상태로 반환됨
        print(f"[agent] ⏳ 긴 작업 시작 task={task_id}")

        await asyncio.sleep(5)  # ← long-running task 시뮬레이션

        print(f"[agent] ✅ 작업 완료 → 완료 push 전송 task={task_id}")
        await updater.complete(  # completed → push notification 자동 발사
            message=new_agent_text_message("작업 완료! 결과=42", context_id, task_id)
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        pass


def build():
    card = AgentCard(
        name="Long Task Agent",
        description="긴 작업 후 push notification 을 보내는 데모",
        version="0.1.0",
        url="http://127.0.0.1:9101/",
        protocol_version="0.3.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=False, push_notifications=True),
        skills=[
            AgentSkill(
                id="long_task",
                name="Long Task",
                description="오래 걸리는 작업 후 완료 알림",
                tags=["demo", "push"],
            )
        ],
    )
    httpx_client = httpx.AsyncClient()
    config_store = InMemoryPushNotificationConfigStore()
    handler = DefaultRequestHandler(
        agent_executor=LongTaskExecutor(),
        task_store=InMemoryTaskStore(),
        push_config_store=config_store,  # 클라이언트가 보낸 webhook URL 저장
        push_sender=BasePushNotificationSender(httpx_client, config_store),  # 완료 시 POST
    )
    return A2AStarletteApplication(agent_card=card, http_handler=handler).build()


if __name__ == "__main__":
    uvicorn.run(build(), host="127.0.0.1", port=9101)
