import logging
from threading import Lock
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from google.auth.exceptions import RefreshError
from openai import APIConnectionError, APIStatusError, APITimeoutError
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from react_agent.backend.agent.harness import Harness
from react_agent.backend.auth.auth import (
    get_current_user,
)
from react_agent.backend.config import settings
from react_agent.backend.db.database import get_db
from react_agent.backend.db.models import Conversation, Message, User

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_active_chat_traces: dict[str, tuple[int, list[dict[str, str]]]] = {}
_active_chat_traces_lock = Lock()

router = APIRouter(
    prefix="/api/chat",
    tags=["Chat"],
)


def get_harness(request: Request) -> Harness:
    return request.app.state.harness


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


@router.get(
    "/{trace_id}/progress",
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


@router.post(
    "/",
    response_model=ChatResponse,
)
def chat(
    request: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    harness: Harness = Depends(get_harness),
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
