from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from react_agent.agent.agent import Agent
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
from react_agent.db.database import Base, engine, get_db
from react_agent.db.models import Conversation, Message, User
from react_agent.llm.client import LLMClient
from react_agent.agent.harness import Harness
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

# App setup
app = FastAPI(lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        #"*"
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
    existing_user = (
    db.query(User)
    .filter(User.email == request.email)
    .first()
    )

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
    user = (
    db.query(User)
    .filter(User.email == request.email)
    .first()
    )

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

    # Создаем историю сообщений для передачи в агент
    history = [
        {
            "role": message.role,
            "content": message.content,
        }
        for message in conversation.messages
    ]

    # Запускаем агента
    response = harness.run(
        history=history,
        user_input=request.message,
    )

    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=response,
    )

    # Только после обработки агентом запроса от юзера добавляем сообщение юзера в базу данных
    try:
        db.add_all([user_message, assistant_message])

        if conversation.title is None:
            def get_title(text: str) -> str:
                return text.strip()[:100] # Dummy title
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
        conversation_id=conversation.id,
    )
