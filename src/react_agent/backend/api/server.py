import json
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from threading import Lock
from uuid import UUID

import jwt
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from google.auth.exceptions import RefreshError
from openai import APIConnectionError, APIStatusError, APITimeoutError
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from react_agent.backend.agent.agent import Agent
from react_agent.backend.agent.harness import Harness
from react_agent.backend.auth.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from react_agent.backend.auth.schemas import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)
from react_agent.backend.config import settings
from react_agent.backend.db.database import Base, engine, get_db
from react_agent.backend.db.models import Conversation, Message, User
from react_agent.backend.integrations.credentials import (
    ALLOWED_PROVIDERS,
    delete_credentials,
    get_credentials,
    save_credentials,
)
from react_agent.backend.integrations.github import validate_github_token
from react_agent.backend.integrations.google_oauth import create_google_flow
from react_agent.backend.integrations.jira import validate_jira_credentials
from react_agent.backend.integrations.oauth_state import (
    consume_google_oauth_state,
    save_google_oauth_state,
)
from react_agent.backend.llm.client import LLMClient
from react_agent.backend.llm.prompts import load_system_prompt, load_tools_prompt

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_active_chat_traces: dict[str, tuple[int, list[dict[str, str]]]] = {}
_active_chat_traces_lock = Lock()


def _ensure_message_tool_trace_column(database_engine: Engine = engine) -> None:
    columns = inspect(database_engine).get_columns("messages")
    if "tool_trace" in {column["name"] for column in columns}:
        return

    with database_engine.begin() as connection:
        connection.execute(text("ALTER TABLE messages ADD COLUMN tool_trace JSON"))


def _find_llm_error(
    error: BaseException,
) -> APIStatusError | APIConnectionError | None:
    if isinstance(error, (APIStatusError, APIConnectionError)):
        return error
    if isinstance(error, ExceptionGroup):
        for nested_error in error.exceptions:
            match = _find_llm_error(nested_error)
            if match is not None:
                return match
    return None


def _llm_error_detail(error: APIStatusError | APIConnectionError) -> str:
    detail = None

    if isinstance(error, APIStatusError) and isinstance(error.body, dict):
        body = error.body
        provider_error = body.get("error")
        if isinstance(provider_error, dict):
            detail = (
                provider_error.get("message")
                or provider_error.get("detail")
                or provider_error.get("code")
            )
        elif isinstance(provider_error, str):
            detail = provider_error
        if not detail:
            detail = body.get("message") or body.get("detail")

    if isinstance(error, APITimeoutError):
        detail = "истекло время ожидания ответа"
    elif not isinstance(detail, str) or not detail.strip():
        detail = str(error)

    cause = error.__cause__
    if cause is not None and str(cause).strip():
        detail = f"{detail}: {cause}"

    detail = " ".join(detail.split())
    if settings.LLM_API_KEY:
        detail = detail.replace(settings.LLM_API_KEY, "[REDACTED]")
    return detail[:600]


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ready = False
    logger.info("Lifespan entered")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized")
    _ensure_message_tool_trace_column()
    logger.info("Message tool_trace column checked")

    try:
        # Create KV-cache on warmup
        logger.info("Starting LLM warmup")
        system_prompt = load_system_prompt()
        tools_prompt = load_tools_prompt()
        context = system_prompt + "\n\n" + tools_prompt
        logger.info("Warmup context length: %d characters", len(context))
        response = llm_client.warmup(context)
        app.state.ready = True
        logger.info(f"LLM warmup completed with response: {response}")
    except Exception:
        logger.exception("LLM warmup failed")

    yield


# App setup
app = FastAPI(lifespan=lifespan)

Instrumentator().instrument(app).expose(
    app,
    include_in_schema=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        # "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Agent setup
MAX_TOOL_ROUNDS = 10

llm_client = LLMClient()
agent = Agent(llm_client)
harness = Harness(agent, max_tool_rounds=MAX_TOOL_ROUNDS)


# ===================== Health =====================
@app.get("/health")
def health():
    if not app.state.ready:
        raise HTTPException(status_code=503, detail="Backend is not ready")

    return {"status": "ready"}


# ===================== AUTH =====================
@app.post(
    "/api/auth/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db),
):
    existing_user = db.query(User).filter(User.email == request.email).first()

    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already exists",
        )

    user = User(
        email=request.email,
        password_hash=hash_password(request.password),
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)

    return AuthResponse(
        access_token=token,
    )


@app.post(
    "/api/auth/login",
    response_model=AuthResponse,
)
def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == request.email).first()

    if user is None or not verify_password(
        request.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(user.id)

    return AuthResponse(
        access_token=token,
    )


@app.get(
    "/api/auth/me",
    response_model=UserResponse,
)
def me(
    user: User = Depends(get_current_user),
):
    return UserResponse(
        id=user.id,
        email=user.email,
    )


class JiraCredentialsRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    api_token: str = Field(min_length=1, max_length=1000)


class GitHubCredentialsRequest(BaseModel):
    token: str = Field(min_length=1, max_length=1000)


@app.get("/api/integrations")
def list_integrations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {
        provider: get_credentials(db, user_id=user.id, provider=provider) is not None
        for provider in sorted(ALLOWED_PROVIDERS)
    }


@app.put("/api/integrations/jira")
async def connect_jira(
    request: JiraCredentialsRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    credentials = request.model_dump()
    try:
        valid = await validate_jira_credentials(credentials)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Jira credentials were rejected",
        )
    try:
        save_credentials(
            db,
            user_id=user.id,
            provider="jira",
            credentials=credentials,
        )
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Integration credential storage is unavailable",
        ) from error
    return {"connected": True}


@app.put("/api/integrations/github")
def connect_github(
    request: GitHubCredentialsRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        valid = validate_github_token(request.token)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="GitHub token was rejected",
        )
    try:
        save_credentials(
            db,
            user_id=user.id,
            provider="github",
            credentials={"token": request.token},
        )
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Integration credential storage is unavailable",
        ) from error
    return {"connected": True}


@app.delete("/api/integrations/{provider}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_integration(
    provider: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if provider not in ALLOWED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )
    delete_credentials(db, user_id=user.id, provider=provider)


@app.get("/api/integrations/google_calendar/auth-url")
def google_calendar_auth_url(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    nonce = secrets.token_urlsafe(24)
    state = jwt.encode(
        {
            "sub": str(user.id),
            "purpose": "google_calendar_oauth",
            "nonce": nonce,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    try:
        flow = create_google_flow(state=state)
        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        save_google_oauth_state(
            db,
            nonce=nonce,
            user_id=user.id,
            code_verifier=flow.code_verifier,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
    except (OSError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Calendar OAuth is not configured",
        ) from error
    return {"authorization_url": authorization_url}


@app.get("/api/integrations/google_calendar/callback")
def google_calendar_callback(
    code: str | None = None,
    state: str = "",
    error: str | None = None,
    db: Session = Depends(get_db),
):
    if error or not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Calendar authorization was not completed",
        )
    try:
        payload = jwt.decode(
            state,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={
                "require": ["exp", "sub", "nonce", "purpose"],
            },
        )
    except jwt.PyJWTError as exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state",
        ) from exception

    if payload.get("purpose") != "google_calendar_oauth":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state",
        )
    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id.isdecimal():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state",
        )
    if db.get(User, int(user_id)) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    nonce = payload.get("nonce")
    if not isinstance(nonce, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state",
        )

    code_verifier = consume_google_oauth_state(
        db,
        nonce=nonce,
        user_id=int(user_id),
    )

    if code_verifier is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth session expired or already used",
        )
    try:
        flow = create_google_flow(
            state=state,
            code_verifier=code_verifier,
            autogenerate_code_verifier=False,
        )
        flow.fetch_token(code=code)
        credentials = json.loads(flow.credentials.to_json())
        save_credentials(
            db,
            user_id=int(user_id),
            provider="google_calendar",
            credentials=credentials,
        )
    except Exception as exception:
        logger.exception("Google Calendar OAuth callback failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not complete Google Calendar authorization",
        ) from exception

    return RedirectResponse(
        url=f"{settings.FRONTEND_URL}/?integration=google_calendar",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ===================== CONVERSATIONS =====================
class ConversationResponse(BaseModel):
    id: int
    title: str | None


class RenameConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)


@app.get(
    "/api/conversations",
    response_model=list[ConversationResponse],
)
def get_conversations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversations = (
        db.query(Conversation)
        .filter(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )

    return [
        ConversationResponse(
            id=conversation.id,
            title=conversation.title,
        )
        for conversation in conversations
    ]


@app.delete(
    "/api/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        )
        .first()
    )

    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    db.delete(conversation)
    db.commit()


@app.patch(
    "/api/conversations/{conversation_id}",
    response_model=ConversationResponse,
)
def rename_conversation(
    conversation_id: int,
    request: RenameConversationRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    title = request.title.strip()

    if not title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Title cannot be empty",
        )

    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        )
        .first()
    )

    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    conversation.title = title
    db.commit()
    db.refresh(conversation)

    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
    )


class MessageResponse(BaseModel):
    role: str
    content: str
    tool_trace: list[dict[str, str]] = Field(default_factory=list)


@app.get(
    "/api/conversations/{conversation_id}/messages",
    response_model=list[MessageResponse],
)
def get_messages(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        )
        .first()
    )

    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    return [
        MessageResponse(
            role=message.role,
            content=message.content,
            tool_trace=message.tool_trace or [],
        )
        for message in conversation.messages
    ]


# ===================== CHAT =====================
class ChatRequest(BaseModel):
    message: str
    conversation_id: int | None = None
    trace_id: UUID | None = None


class ChatResponse(BaseModel):
    response: str
    conversation_id: int
    tool_trace: list[dict[str, str]] = Field(default_factory=list)


class ChatProgressResponse(BaseModel):
    tool_trace: list[dict[str, str]]
    running: bool = True


@app.get(
    "/api/chat/{trace_id}/progress",
    response_model=ChatProgressResponse,
)
def get_chat_progress(
    trace_id: UUID,
    user: User = Depends(get_current_user),
):
    with _active_chat_traces_lock:
        active_trace = _active_chat_traces.get(str(trace_id))
        if active_trace is None or active_trace[0] != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat progress not found",
            )

        return ChatProgressResponse(tool_trace=list(active_trace[1]))


@app.post(
    "/api/chat",
    response_model=ChatResponse,
)
def chat(
    request: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not request.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message cannot be empty",
        )

    if request.conversation_id is None:
        conversation = Conversation(
            user_id=user.id,
        )

        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    else:
        conversation = (
            db.query(Conversation)
            .filter(
                Conversation.id == request.conversation_id,
                Conversation.user_id == user.id,
            )
            .first()
        )

        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

    # Получаем сообщение
    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=request.message,
    )

    conversation_id = conversation.id
    user_id = user.id

    # Создаем историю сообщений для передачи в агент
    history = [
        {
            "role": message.role,
            "content": message.content,
        }
        for message in conversation.messages
    ]

    db.rollback()

    # Запускаем агента
    tool_trace: list[dict[str, str]] = []
    trace_id = str(request.trace_id) if request.trace_id else None
    if trace_id:
        with _active_chat_traces_lock:
            _active_chat_traces[trace_id] = (user_id, tool_trace)

    try:
        try:
            response = harness.run(
                history=history,
                user_input=request.message,
                workspace_id=user_id,
                user_id=user_id,
                db=db,
                tool_trace=tool_trace,
            )
        except (APIStatusError, APIConnectionError, ExceptionGroup) as error:
            provider_error = _find_llm_error(error)
            if provider_error is None:
                raise

            provider_detail = _llm_error_detail(provider_error)
            if isinstance(provider_error, APIConnectionError):
                logger.warning(
                    "Could not connect to LLM provider: %s",
                    provider_detail,
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Не удалось получить ответ от LLM-провайдера: {provider_detail}",
                ) from error

            logger.warning(
                "LLM provider rejected chat request with HTTP %s: %s",
                provider_error.status_code,
                provider_detail,
            )
            if provider_error.status_code == 413:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        "LLM-провайдер отклонил запрос из-за размера или лимита токенов: "
                        f"{provider_detail}"
                    ),
                ) from error
            if provider_error.status_code == 429:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"LLM-провайдер ограничил частоту запросов: {provider_detail}",
                ) from error
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    f"LLM-провайдер вернул HTTP {provider_error.status_code}: "
                    f"{provider_detail}"
                ),
            ) from error
        except RefreshError as error:
            logger.warning("Google Calendar token refresh failed: %s", error)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Google Calendar authorization has expired or been revoked. "
                    "Reconnect Google Calendar in Integrations."
                ),
            ) from error
        except Exception as error:
            logger.exception("Unexpected error while running chat agent")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Ошибка выполнения агента: {error}",
            ) from error
    finally:
        if trace_id:
            with _active_chat_traces_lock:
                _active_chat_traces.pop(trace_id, None)

    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
        .with_for_update()
        .first()
    )

    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation was deleted while agent was running",
        )

    assistant_message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=response,
        tool_trace=tool_trace,
    )

    # Только после обработки агентом запроса от юзера добавляем сообщение юзера в базу данных
    try:
        db.add_all([user_message, assistant_message])

        if conversation.title is None:

            def get_title(text: str) -> str:
                return text.strip()[:100]  # Dummy title

            conversation.title = get_title(request.message)

        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception("Failed to save chat messages")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save messages: {e}",
        ) from e
    return ChatResponse(
        response=response,
        conversation_id=conversation_id,
        tool_trace=tool_trace,
    )
