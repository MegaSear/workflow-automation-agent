import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from react_agent.backend.agent.agent import Agent
from react_agent.backend.agent.harness import Harness
from react_agent.backend.api.routers import auth, chat, conversations, integrations
from react_agent.backend.config import settings
from react_agent.backend.db.database import Base, engine
from react_agent.backend.llm.client import LLMClient

logger = logging.getLogger(__name__)


# Agent setup
llm_client = LLMClient()
agent = Agent(llm_client)
harness = Harness(agent, max_tool_rounds=settings.MAX_TOOL_ROUNDS)


def _ensure_message_tool_trace_column(database_engine: Engine = engine) -> None:
    columns = inspect(database_engine).get_columns("messages")
    if "tool_trace" in {column["name"] for column in columns}:
        return

    with database_engine.begin() as connection:
        connection.execute(text("ALTER TABLE messages ADD COLUMN tool_trace JSON"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ready = False
    logger.info("Lifespan entered")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized")
    _ensure_message_tool_trace_column()
    logger.info("Message tool_trace column checked")

    if settings.LLM_WARMUP_ENABLED:
        try:
            # Create KV-cache on warmup
            logger.info("Starting LLM warmup")

            messages = agent.build_messages(history=[], user_input="")
            response = llm_client.warmup(messages)

            usage = response.usage

            if usage is not None:
                logger.info(
                    "Warmup prompt tokens: %d",
                    usage.prompt_tokens,
                )
            else:
                logger.warning("LLM warmup response does not contain token usage")

            logger.info(f"LLM warmup completed with response: {response}")
        except Exception:
            logger.exception("LLM warmup failed")
    else:
        logger.info("LLM warmup disabled")

    app.state.ready = True
    app.state.harness = harness
    yield


# App setup
app = FastAPI(lifespan=lifespan)

app.include_router(auth.router)
app.include_router(integrations.router)
app.include_router(conversations.router)
app.include_router(chat.router)

Instrumentator().instrument(app).expose(
    app,
    include_in_schema=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===================== Health =====================
@app.get("/health")
def health():
    if not app.state.ready:
        raise HTTPException(status_code=503, detail="Backend is not ready")

    return {"status": "ready"}
