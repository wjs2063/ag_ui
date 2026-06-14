import json

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState
from a2a.utils.message import new_agent_text_message
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
    messages_from_dict,
)
from langchain_openai import ChatOpenAI

from pocs.interrupt_pattern.config import OPENAI_MODEL

_llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0.7)

_SYSTEM = (
    "너는 사용자에게 계속 추가 정보를 묻는 대화 도우미야. "
    "이전 대화 히스토리를 참고해 맥락에 맞게 답하고, 사용자의 입력에 한국어로 아주 "
    "짧게 반응한 뒤, 더 알아내기 위한 후속 질문을 한 문장으로 해. 대화를 절대 끝내지 마."
)


def _extract(message) -> tuple[str, list[BaseMessage]]:
    """요청 메시지의 DataPart 에서 (question, history) 를 추출한다."""
    for part in message.parts:
        root = part.root
        if root.kind == "data":
            data = root.data or {}
            meta = root.metadata or {}
            history = messages_from_dict(meta.get("history") or [])
            return data.get("question") or "", history
    return "", []  # DataPart 가 없으면 빈 입력


class LangGraphExecutor(AgentExecutor):
    def __init__(self, graph=None):
        self.graph = graph  # 미사용(호환용)

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        task_id = context.task_id or context.message.message_id
        context_id = context.context_id or task_id

        question, history = _extract(context.message)
        print(f"\n[A2A server] ▶ execute  task_id={task_id} context_id={context_id}")
        print(f"[A2A server]   question={question!r}  history={len(history)}개")
        for m in history:
            print(f"[A2A server]     · {type(m).__name__}: {m.content}")

        updater = TaskUpdater(event_queue, task_id, context_id)
        if not context.current_task:
            print(f"[A2A server]   event → TaskState.submitted")
            await updater.submit()
        print(f"[A2A server]   event → TaskState.working")
        await updater.start_work()

        # history + 현재 question 으로 맥락을 반영해 LLM 응답 생성 → 항상 input_required
        llm_input = (
            [SystemMessage(content=_SYSTEM)]
            + history
            + [HumanMessage(content=question or "(빈 입력)")]
        )
        ai = await _llm.ainvoke(llm_input)
        print(f"[A2A server]   LLM 응답={ai.content!r}")
        payload = {"type": "ask", "question": ai.content}
        print(f"[A2A server]   event → TaskState.input_required (final=True)")
        await updater.update_status(
            TaskState.input_required,
            message=new_agent_text_message(
                json.dumps(payload, ensure_ascii=False), context_id, task_id
            ),
            final=True,
        )

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        task_id = context.task_id or (
            context.message.message_id if context.message else "unknown"
        )
        context_id = context.context_id or task_id
        updater = TaskUpdater(event_queue, task_id, context_id)
        await updater.cancel()
