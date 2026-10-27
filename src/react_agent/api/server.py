import json
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from google_auth_oauthlib.flow import Flow
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from react_agent.agent.agent import Agent
from react_agent.agent.harness import Harness
from react_agent.agent.tools.jira import validate_jira_credentials
from react_agent.auth.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from react_agent.auth.schemas import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)
from react_agent.config import settings
from react_agent.db.database import Base, engine, get_db
from react_agent.db.models import Conversation, Message, User, UserIntegration
from react_agent.integrations.credentials import (
    delete_credentials,
    save_credentials,
)
from react_agent.llm.client import LLMClient

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
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

agent = Agent(LLMClient())
harness = Harness(agent, max_tool_rounds=MAX_TOOL_ROUNDS)


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
        )
        for message in conversation.messages
    ]


# ===================== CHAT =====================
class ChatRequest(BaseModel):
    message: str
    conversation_id: int | None = None


class ChatResponse(BaseModel):
    response: str
    conversation_id: int


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
    response = harness.run(
        history=history,
        user_input=request.message,
        workspace_id=user_id,
        user_id=user_id,
        db=db,
    )

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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save messages",
        ) from e
    return ChatResponse(
        response=response,
        conversation_id=conversation_id,
    )


class JiraCredentialsRequest(BaseModel):
    base_url: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    api_token: str = Field(min_length=1, max_length=4096)


@app.get("/api/integrations")
def get_integrations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    providers = {
        row[0]
        for row in db.query(UserIntegration.provider)
        .filter(UserIntegration.user_id == user.id)
        .all()
    }

    return {
        "jira": "jira" in providers,
        "google_calendar": "google_calendar" in providers,
    }


@app.put("/api/integrations/jira")
def connect_jira(
    request: JiraCredentialsRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        base_url = validate_jira_credentials(
            request.base_url,
            request.email,
            request.api_token,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    except httpx.HTTPStatusError as error:
        code = error.response.status_code

        if code in (401, 403):
            detail = "Jira rejected these credentials"
            http_status = status.HTTP_400_BAD_REQUEST
        else:
            detail = "Could not verify Jira credentials"
            http_status = status.HTTP_502_BAD_GATEWAY

        raise HTTPException(
            status_code=http_status,
            detail=detail,
        ) from error
    except httpx.RequestError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach Jira",
        ) from error

    save_credentials(
        db,
        user_id=user.id,
        provider="jira",
        credentials={
            "base_url": base_url,
            "email": request.email.strip(),
            "api_token": request.api_token,
        },
    )

    return {"provider": "jira", "connected": True}


@app.delete("/api/integrations/jira")
def disconnect_jira(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    delete_credentials(
        db,
        user_id=user.id,
        provider="jira",
    )

    return {"provider": "jira", "connected": False}


GOOGLE_CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
]
GOOGLE_OAUTH_STATE_COOKIE = "google_calendar_oauth_state"
GOOGLE_OAUTH_COOKIE_MAX_AGE = 600


def _create_google_flow(*, state: str | None = None) -> Flow:
    return Flow.from_client_secrets_file(
        str(settings.GOOGLE_CALENDAR_CREDENTIALS_FILE),
        scopes=GOOGLE_CALENDAR_SCOPES,
        state=state,
        redirect_uri=settings.GOOGLE_CALENDAR_REDIRECT_URI,
    )


@app.get("/api/integrations/google_calendar/auth-url")
def google_calendar_auth_url(
    user: User = Depends(get_current_user),
):
    flow = _create_google_flow()

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    # Сохраняем state и PKCE verifier в подписанной cookie.
    cookie_payload = jwt.encode(
        {
            "sub": str(user.id),
            "state": state,
            "code_verifier": flow.code_verifier,
            "exp": datetime.now(timezone.utc)
            + timedelta(seconds=GOOGLE_OAUTH_COOKIE_MAX_AGE),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    response = JSONResponse({"authorization_url": authorization_url})
    response.set_cookie(
        key=GOOGLE_OAUTH_STATE_COOKIE,
        value=cookie_payload,
        httponly=True,
        secure=False,  # Только локальная разработка по HTTP.
        samesite="lax",
        max_age=GOOGLE_OAUTH_COOKIE_MAX_AGE,
        path="/api/integrations/google_calendar",
    )
    return response


@app.get("/api/integrations/google_calendar/callback")
def google_calendar_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    cookie = request.cookies.get(GOOGLE_OAUTH_STATE_COOKIE)
    state = request.query_params.get("state")

    if not cookie or not state:
        raise HTTPException(
            status_code=400,
            detail="Missing OAuth state or verification cookie",
        )

    try:
        payload = jwt.decode(
            cookie,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["sub", "state", "code_verifier", "exp"]},
        )
    except jwt.PyJWTError as error:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired OAuth session",
        ) from error

    if not secrets.compare_digest(payload["state"], state):
        raise HTTPException(
            status_code=400,
            detail="OAuth state verification failed",
        )

    if request.query_params.get("error"):
        raise HTTPException(
            status_code=400,
            detail="Google Calendar authorization was denied",
        )

    user_id = int(payload["sub"])
    if user_id <= 0 or db.get(User, user_id) is None:
        raise HTTPException(status_code=400, detail="Invalid OAuth user")

    try:
        flow = _create_google_flow(state=state)
        flow.code_verifier = payload["code_verifier"]
        flow.fetch_token(authorization_response=str(request.url))
        credentials = flow.credentials
    except Exception as error:
        print("Google Calendar OAuth callback failed:", repr(error))
        raise HTTPException(
            status_code=400,
            detail="Could not complete Google Calendar authorization",
        ) from error

    save_credentials(
        db,
        user_id=user_id,
        provider="google_calendar",
        credentials=json.loads(credentials.to_json()),
    )
    response = RedirectResponse(
        url=f"{settings.FRONTEND_URL}/",
        status_code=303,
    )
    response.delete_cookie(
        key=GOOGLE_OAUTH_STATE_COOKIE,
        path="/api/integrations/google_calendar",
    )
    return response


@app.delete("/api/integrations/google_calendar")
def disconnect_google_calendar(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    delete_credentials(
        db,
        user_id=user.id,
        provider="google_calendar",
    )

    return {"provider": "google_calendar", "connected": False}
