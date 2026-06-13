import json

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState
from a2a.utils.message import new_agent_text_message
from langgraph.types import Command


class LangGraphExecutor(AgentExecutor):
    """A2A AgentExecutor backed by a LangGraph that uses `interrupt()`.

    Maps:
      - A2A task_id -> LangGraph thread_id (1:1)
      - LangGraph interrupt -> A2A TaskState.input_required
      - Follow-up A2A message -> Command(resume=user_text)
    """

    def __init__(self, graph):
        self.graph = graph

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        task_id = context.task_id or context.message.message_id
        context_id = context.context_id or task_id
        thread_id = context.context_id or task_id
        cfg = {"configurable": {"thread_id": thread_id}}

        user_text = context.get_user_input() or ""

        updater = TaskUpdater(event_queue, task_id, context_id)
        if not context.current_task:
            await updater.submit()
        await updater.start_work()

        snap = await self.graph.aget_state(cfg)
        has_interrupt = bool(snap.tasks) and any(t.interrupts for t in snap.tasks)

        if has_interrupt:
            resume_value = self._parse_resume(user_text, snap)
            result = await self.graph.ainvoke(Command(resume=resume_value), cfg)
        else:
            result = await self.graph.ainvoke({"message": user_text}, cfg)

        if "__interrupt__" in result and result["__interrupt__"]:
            payload = result["__interrupt__"][0].value
            prompt = (
                payload
                if isinstance(payload, str)
                else payload.get("question") or json.dumps(payload, ensure_ascii=False)
            )
            await updater.update_status(
                TaskState.input_required,
                message=new_agent_text_message(prompt, context_id, task_id),
                final=True,
            )
            return

        response_text = result.get("response", "(no response)")
        await updater.update_status(
            TaskState.completed,
            message=new_agent_text_message(response_text, context_id, task_id),
            final=True,
        )

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        task_id = context.task_id or (context.message.message_id if context.message else "unknown")
        context_id = context.context_id or task_id
        updater = TaskUpdater(event_queue, task_id, context_id)
        await updater.cancel()

    def _parse_resume(self, user_text: str, snap) -> object:
        pending = next(
            (t.interrupts[0] for t in snap.tasks if t.interrupts), None
        )
        if pending is None:
            return user_text

        value = pending.value
        if isinstance(value, str):
            return user_text

        stripped = user_text.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                pass

        if isinstance(value, dict) and value.get("type") == "confirm":
            choice = stripped.lower()
            if choice not in ("yes", "no"):
                choice = "yes" if choice in ("y", "동의", "ok") else "no"
            return {"choice": choice}

        if isinstance(value, dict) and value.get("type") == "tool_review":
            action = stripped.lower()
            if action not in ("approve", "reject", "edit"):
                action = "approve" if action in ("ok", "yes", "승인") else "reject"
            return {"action": action, "note": user_text}

        return user_text
