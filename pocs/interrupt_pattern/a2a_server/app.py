from contextlib import asynccontextmanager

from a2a.server.apps.jsonrpc.starlette_app import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from starlette.applications import Starlette

from pocs.interrupt_pattern.a2a_server.executor import LangGraphExecutor
from pocs.interrupt_pattern.checkpointer import lifespan_checkpointer
from pocs.interrupt_pattern.config import A2A_HOST, A2A_PORT, DATABASE_URL
from pocs.interrupt_pattern.graph import build_graph


def build_agent_card(url: str) -> AgentCard:
    skill = AgentSkill(
        id="interrupt_chat",
        name="Interrupt Chat",
        description="LangGraph interrupt-driven chat: ask name → confirm → tool review.",
        tags=["a2a", "langgraph", "interrupt"],
        examples=["hello", "안녕"],
        input_modes=["text/plain"],
        output_modes=["text/plain"],
    )
    return AgentCard(
        name="Interrupt Pattern Agent",
        description="POC agent demonstrating LangGraph interrupt() over A2A.",
        version="0.1.0",
        url=url,
        protocol_version="0.3.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[skill],
    )


def build_a2a_app(graph, url: str) -> Starlette:
    request_handler = DefaultRequestHandler(
        agent_executor=LangGraphExecutor(graph),
        task_store=InMemoryTaskStore(),
    )
    a2a_app = A2AStarletteApplication(
        agent_card=build_agent_card(url),
        http_handler=request_handler,
    )
    return a2a_app.build()


def build_app_with_lifespan() -> Starlette:
    @asynccontextmanager
    async def lifespan(app):
        async with lifespan_checkpointer(DATABASE_URL) as saver:
            graph = build_graph(saver)
            url = f"http://{A2A_HOST}:{A2A_PORT}/"
            request_handler = DefaultRequestHandler(
                agent_executor=LangGraphExecutor(graph),
                task_store=InMemoryTaskStore(),
            )
            a2a_inner = A2AStarletteApplication(
                agent_card=build_agent_card(url),
                http_handler=request_handler,
            )
            inner_app = a2a_inner.build()
            app.router.routes.extend(inner_app.router.routes)
            app.state.graph = graph
            yield

    return Starlette(lifespan=lifespan)
