"""
API tests covering authentication, authorization, conversation management,
and chat functionality.

The tests verify:
- User registration, password hashing, login, and JWT authentication.
- Access control and isolation of users' conversations and messages.
- Conversation listing, renaming, and deletion.
- Input validation and handling of invalid requests.
- Chat creation, message persistence, and conversation history.
- Correct HTTP status codes and database state after operations.

External LLM execution is mocked to keep tests deterministic and independent
of network access and API credentials.
"""

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.fernet import Fernet
from google.auth.exceptions import RefreshError
from openai import APIConnectionError, APIStatusError, APITimeoutError
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from react_agent.backend.api import server
from react_agent.backend.api.routers import chat as chat_router
from react_agent.backend.api.routers import integrations as integrations_router
from react_agent.backend.api.server import app
from react_agent.backend.auth.auth import get_current_user, hash_password
from react_agent.backend.config import settings
from react_agent.backend.db.models import Conversation, Message, User
from react_agent.backend.integrations.credentials import (
    get_credentials,
    save_credentials,
)


def test_existing_messages_table_gets_tool_trace_column():
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE messages (id INTEGER PRIMARY KEY, content TEXT NOT NULL)"
            )

        server._ensure_message_tool_trace_column(engine)

        columns = {column["name"] for column in inspect(engine).get_columns("messages")}
        assert "tool_trace" in columns
    finally:
        engine.dispose()


# ==================== CONVERSATION ACCESS ====================


def test_cannot_read_another_users_messages(
    client,
    db_session,
    test_user,
):
    """A user cannot read messages from someone else's conversation."""
    other_user = User(
        email="other@example.com",
        password_hash="unused",
    )
    db_session.add(other_user)
    db_session.commit()
    db_session.refresh(other_user)

    conversation = Conversation(
        user_id=other_user.id,
        title="Private conversation",
    )
    db_session.add(conversation)
    db_session.commit()
    db_session.refresh(conversation)

    db_session.add(
        Message(
            conversation_id=conversation.id,
            role="user",
            content="Private message",
        )
    )
    db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: test_user

    try:
        response = client.get(f"/api/conversations/{conversation.id}/messages")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 404
    assert "Private message" not in response.text


def test_cannot_rename_another_users_conversation(
    client,
    db_session,
    test_user,
):
    other_user = User(
        email="other@example.com",
        password_hash="unused",
    )
    db_session.add(other_user)
    db_session.commit()
    db_session.refresh(other_user)

    conversation = Conversation(
        user_id=other_user.id,
        title="Original title",
    )
    db_session.add(conversation)
    db_session.commit()
    db_session.refresh(conversation)

    app.dependency_overrides[get_current_user] = lambda: test_user

    try:
        response = client.patch(
            f"/api/conversations/{conversation.id}",
            json={"title": "Hacked title"},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 404

    db_session.refresh(conversation)
    assert conversation.title == "Original title"


def test_cannot_delete_another_users_conversation(
    client,
    db_session,
    test_user,
):
    other_user = User(
        email="other@example.com",
        password_hash="unused",
    )
    db_session.add(other_user)
    db_session.commit()
    db_session.refresh(other_user)

    conversation = Conversation(
        user_id=other_user.id,
        title="Private conversation",
    )
    db_session.add(conversation)
    db_session.commit()
    db_session.refresh(conversation)

    conversation_id = conversation.id

    app.dependency_overrides[get_current_user] = lambda: test_user

    try:
        response = client.delete(f"/api/conversations/{conversation_id}")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 404

    remaining = (
        db_session.query(Conversation)
        .filter(Conversation.id == conversation_id)
        .first()
    )
    assert remaining is not None


# ==================== EMPTY MESSAGE ====================


@pytest.mark.parametrize("message", ["", " ", "   ", "\t\n"])
def test_chat_rejects_empty_message(
    authenticated_client,
    db_session,
    monkeypatch,
    message,
):
    """Empty or whitespace-only messages must not reach the agent."""

    def fail_if_called(*args, **kwargs):
        pytest.fail("Agent must not run for an empty message")

    monkeypatch.setattr(server.harness, "run", fail_if_called)

    response = authenticated_client.post(
        "/api/chat",
        json={"message": message},
    )

    assert response.status_code == 400

    # No conversation should be created for an invalid message.
    assert db_session.query(Conversation).count() == 0
    assert db_session.query(Message).count() == 0


# ==================== CHAT AND MESSAGE PERSISTENCE ====================


def test_chat_creates_conversation_and_saves_messages(
    authenticated_client,
    db_session,
    test_user,
    monkeypatch,
):
    """A new chat creates a conversation and saves both messages."""

    async def fake_run(history, user_input, *, workspace_id, user_id, db, tool_trace):
        assert history == []
        assert user_input == "Hello"
        assert workspace_id == test_user.id
        assert user_id == test_user.id
        assert db is not None
        tool_trace.append({"name": "my_default__get_current_time", "status": "success"})
        return "Hello! How can I help?"

    monkeypatch.setattr(server.harness, "run", fake_run)

    response = authenticated_client.post(
        "/api/chat",
        json={"message": "Hello"},
    )

    assert response.status_code == 200

    data = response.json()
    assert data["response"] == "Hello! How can I help?"
    assert data["tool_trace"] == [
        {"name": "my_default__get_current_time", "status": "success"}
    ]
    assert isinstance(data["conversation_id"], int)

    conversation = (
        db_session.query(Conversation).filter_by(id=data["conversation_id"]).first()
    )

    assert conversation is not None
    assert conversation.user_id == test_user.id

    messages = (
        db_session.query(Message)
        .filter_by(conversation_id=conversation.id)
        .order_by(Message.id)
        .all()
    )

    assert [(m.role, m.content) for m in messages] == [
        ("user", "Hello"),
        ("assistant", "Hello! How can I help?"),
    ]
    assert messages[1].tool_trace == [
        {"name": "my_default__get_current_time", "status": "success"}
    ]

    history_response = authenticated_client.get(
        f"/api/conversations/{conversation.id}/messages"
    )
    assert history_response.status_code == 200
    assert history_response.json()[1]["tool_trace"] == [
        {"name": "my_default__get_current_time", "status": "success"}
    ]


def test_chat_progress_returns_active_trace(
    authenticated_client,
    test_user,
):
    trace_id = uuid4()
    trace = [{"name": "my_default__get_current_time", "status": "running"}]
    key = str(trace_id)

    with chat_router._active_chat_traces_lock:
        chat_router._active_chat_traces[key] = (test_user.id, trace)

    try:
        response = authenticated_client.get(f"/api/chat/{trace_id}/progress")
    finally:
        with chat_router._active_chat_traces_lock:
            chat_router._active_chat_traces.pop(key, None)

    assert response.status_code == 200
    assert response.json() == {"tool_trace": trace, "running": True}


def test_chat_explains_llm_token_limit(
    authenticated_client,
    monkeypatch,
):
    response = httpx.Response(
        413,
        request=httpx.Request("POST", "https://api.example.com/v1/chat/completions"),
    )
    error = APIStatusError(
        "request exceeded provider token limit",
        response=response,
        body={
            "error": {
                "message": "Request too large: requested 10003 tokens, limit is 8000."
            }
        },
    )

    def fail_with_token_limit(*args, **kwargs):
        raise ExceptionGroup("MCP cleanup failed", [error])

    monkeypatch.setattr(server.harness, "run", fail_with_token_limit)

    result = authenticated_client.post(
        "/api/chat",
        json={"message": "Hello"},
    )

    assert result.status_code == 429
    assert "10003 tokens" in result.json()["detail"]
    assert "8000" in result.json()["detail"]


def test_chat_explains_llm_connection_failure(
    authenticated_client,
    monkeypatch,
):
    error = APIConnectionError(
        message="Connection error: provider unavailable",
        request=httpx.Request(
            "POST",
            "https://api.example.com/v1/chat/completions",
        ),
    )

    def fail_with_connection_error(*args, **kwargs):
        raise error

    monkeypatch.setattr(server.harness, "run", fail_with_connection_error)

    result = authenticated_client.post(
        "/api/chat",
        json={"message": "Hello"},
    )

    assert result.status_code == 502
    assert "Не удалось получить ответ от LLM-провайдера" in result.json()["detail"]
    assert "provider unavailable" in result.json()["detail"]


def test_chat_explains_llm_timeout(
    authenticated_client,
    monkeypatch,
):
    error = APITimeoutError(
        request=httpx.Request(
            "POST",
            "https://api.example.com/v1/chat/completions",
        ),
    )

    def fail_with_timeout(*args, **kwargs):
        raise error

    monkeypatch.setattr(server.harness, "run", fail_with_timeout)

    result = authenticated_client.post(
        "/api/chat",
        json={"message": "Hello"},
    )

    assert result.status_code == 502
    assert "истекло время ожидания ответа" in result.json()["detail"]


def test_chat_returns_details_for_unexpected_agent_error(
    authenticated_client,
    monkeypatch,
):
    def fail_with_unexpected_error(*args, **kwargs):
        raise RuntimeError("agent configuration is invalid")

    monkeypatch.setattr(server.harness, "run", fail_with_unexpected_error)

    result = authenticated_client.post(
        "/api/chat",
        json={"message": "Hello"},
    )

    assert result.status_code == 500
    assert result.json()["detail"] == (
        "Ошибка выполнения агента: agent configuration is invalid"
    )


def test_chat_returns_details_when_saving_messages_fails(
    authenticated_client,
    monkeypatch,
):
    original_commit = Session.commit
    commit_count = 0

    def fail_when_saving_messages(session):
        nonlocal commit_count
        commit_count += 1
        if commit_count == 2:
            raise RuntimeError("database is unavailable")
        original_commit(session)

    monkeypatch.setattr(Session, "commit", fail_when_saving_messages)

    async def fake_run(*args, **kwargs):
        return "Hello"

    monkeypatch.setattr(server.harness, "run", fake_run)

    result = authenticated_client.post(
        "/api/chat",
        json={"message": "Hello"},
    )

    assert result.status_code == 500
    assert result.json()["detail"] == (
        "Failed to save messages: database is unavailable"
    )


def test_chat_explains_expired_google_calendar_authorization(
    authenticated_client,
    monkeypatch,
):
    def fail_with_expired_google_token(*args, **kwargs):
        raise RefreshError("invalid_grant: Token has been expired or revoked.")

    monkeypatch.setattr(server.harness, "run", fail_with_expired_google_token)

    result = authenticated_client.post(
        "/api/chat",
        json={"message": "Hello"},
    )

    assert result.status_code == 503
    assert (
        "Google Calendar authorization has expired or been revoked"
        in result.json()["detail"]
    )
    assert "Reconnect Google Calendar" in result.json()["detail"]


# ==================== HISTORY PASSED TO AGENT ====================


def test_chat_passes_existing_history_to_agent(
    authenticated_client,
    db_session,
    test_user,
    monkeypatch,
):
    """The agent receives previous messages before the new user input."""
    conversation = Conversation(
        user_id=test_user.id,
        title="Existing conversation",
    )
    db_session.add(conversation)
    db_session.commit()
    db_session.refresh(conversation)

    db_session.add_all(
        [
            Message(
                conversation_id=conversation.id,
                role="user",
                content="My name is Alex",
            ),
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content="Nice to meet you, Alex!",
            ),
        ]
    )
    db_session.commit()

    expected_history = [
        {"role": "user", "content": "My name is Alex"},
        {
            "role": "assistant",
            "content": "Nice to meet you, Alex!",
        },
    ]

    async def fake_run(history, user_input, *, workspace_id, user_id, db, tool_trace):
        assert history == expected_history
        assert user_input == "What is my name?"
        assert workspace_id == test_user.id
        assert user_id == test_user.id
        assert db is not None
        assert tool_trace == []
        return "Your name is Alex."

    monkeypatch.setattr(server.harness, "run", fake_run)

    response = authenticated_client.post(
        "/api/chat",
        json={
            "message": "What is my name?",
            "conversation_id": conversation.id,
        },
    )

    assert response.status_code == 200
    assert response.json()["response"] == "Your name is Alex."
    assert response.json()["conversation_id"] == conversation.id


def test_integrations_status_is_user_scoped(
    authenticated_client,
    db_session,
    test_user,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "INTEGRATION_ENCRYPTION_KEY",
        Fernet.generate_key().decode("ascii"),
    )
    save_credentials(
        db_session,
        user_id=test_user.id,
        provider="github",
        credentials={"token": "github-test-token"},
    )

    response = authenticated_client.get("/api/integrations")

    assert response.status_code == 200
    assert response.json() == {
        "github": True,
        "google_calendar": False,
        "jira": False,
    }


def test_connect_jira_validates_and_encrypts_credentials(
    authenticated_client,
    db_session,
    test_user,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "INTEGRATION_ENCRYPTION_KEY",
        Fernet.generate_key().decode("ascii"),
    )

    async def valid_jira_credentials(credentials):
        return True

    monkeypatch.setattr(
        integrations_router,
        "validate_jira_credentials",
        valid_jira_credentials,
    )

    response = authenticated_client.put(
        "/api/integrations/jira",
        json={
            "email": "test@example.com",
            "api_token": "jira-test-token",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"connected": True}
    assert get_credentials(
        db_session,
        user_id=test_user.id,
        provider="jira",
    ) == {
        "email": "test@example.com",
        "api_token": "jira-test-token",
    }


def test_connect_github_encrypts_user_token(
    authenticated_client,
    db_session,
    test_user,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "INTEGRATION_ENCRYPTION_KEY",
        Fernet.generate_key().decode("ascii"),
    )
    monkeypatch.setattr(
        integrations_router,
        "validate_github_token",
        lambda token: True,
    )

    response = authenticated_client.put(
        "/api/integrations/github",
        json={"token": "github-test-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"connected": True}
    assert get_credentials(
        db_session,
        user_id=test_user.id,
        provider="github",
    ) == {"token": "github-test-token"}


def test_google_oauth_url_uses_signed_user_state(
    authenticated_client,
    db_session,
    test_user,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "INTEGRATION_ENCRYPTION_KEY",
        Fernet.generate_key().decode("ascii"),
    )

    class FakeFlow:
        code_verifier = "test-code-verifier"

        def authorization_url(self, **kwargs):
            return "https://accounts.google.test/authorize", "state"

    captured = {}

    def create_flow(*, state):
        captured["state"] = state
        return FakeFlow()

    monkeypatch.setattr(integrations_router, "create_google_flow", create_flow)

    response = authenticated_client.get(
        "/api/integrations/google_calendar/auth-url",
    )

    assert response.status_code == 200
    assert response.json() == {
        "authorization_url": "https://accounts.google.test/authorize",
    }
    payload = jwt.decode(
        captured["state"],
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
    assert payload["sub"] == str(test_user.id)
    assert payload["purpose"] == "google_calendar_oauth"


def test_google_oauth_callback_rejects_invalid_state(client):
    response = client.get(
        "/api/integrations/google_calendar/callback",
        params={"code": "authorization-code", "state": "not-a-jwt"},
    )

    assert response.status_code == 400


def test_google_oauth_callback_saves_user_credentials(
    client,
    db_session,
    test_user,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "INTEGRATION_ENCRYPTION_KEY",
        Fernet.generate_key().decode("ascii"),
    )
    state = jwt.encode(
        {
            "sub": str(test_user.id),
            "purpose": "google_calendar_oauth",
            "nonce": "one-time-state",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    def consume_state(db, *, nonce, user_id):
        assert nonce == "one-time-state"
        assert user_id == test_user.id
        return "test-code-verifier"

    monkeypatch.setattr(
        integrations_router,
        "consume_google_oauth_state",
        consume_state,
    )

    class FakeCredentials:
        def to_json(self):
            return json.dumps(
                {
                    "token": "google-access-token",
                    "refresh_token": "google-refresh-token",
                    "expiry": (
                        datetime.now(timezone.utc) + timedelta(hours=1)
                    ).isoformat(),
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "client_id": "test-client",
                    "client_secret": "test-secret",
                }
            )

    class FakeFlow:
        credentials = FakeCredentials()

        def fetch_token(self, *, code):
            assert code == "oauth-code"

    monkeypatch.setattr(
        integrations_router,
        "create_google_flow",
        lambda **kwargs: FakeFlow(),
    )

    response = client.get(
        "/api/integrations/google_calendar/callback",
        params={"code": "oauth-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/?integration=google_calendar")
    stored_credentials = get_credentials(
        db_session,
        user_id=test_user.id,
        provider="google_calendar",
    )
    assert stored_credentials["token"] == "google-access-token"
    assert stored_credentials["refresh_token"] == "google-refresh-token"
    assert stored_credentials["client_id"] == "test-client"


# ==================== REGISTRATION ====================


def test_register_creates_user_and_returns_token(
    client,
    db_session,
):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "new@example.com",
            "password": "StrongPassword123!",
        },
    )

    assert response.status_code == 201
    assert response.json()["access_token"]

    user = db_session.query(User).filter_by(email="new@example.com").first()

    assert user is not None
    assert user.password_hash != "StrongPassword123!"
    assert user.password_hash


def test_register_rejects_duplicate_email(
    client,
    db_session,
):
    password = "StrongPassword123!"

    db_session.add(
        User(
            email="duplicate@example.com",
            password_hash=hash_password(password),
        )
    )
    db_session.commit()

    response = client.post(
        "/api/auth/register",
        json={
            "email": "duplicate@example.com",
            "password": password,
        },
    )

    assert response.status_code == 409
    assert db_session.query(User).filter_by(email="duplicate@example.com").count() == 1


# ==================== LOGIN ====================


def test_login_with_valid_credentials_returns_token(
    client,
    db_session,
):
    password = "StrongPassword123!"

    db_session.add(
        User(
            email="login@example.com",
            password_hash=hash_password(password),
        )
    )
    db_session.commit()

    response = client.post(
        "/api/auth/login",
        json={
            "email": "login@example.com",
            "password": password,
        },
    )

    assert response.status_code == 200
    assert response.json()["access_token"]


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("login@example.com", "WrongPassword123!"),
        ("unknown@example.com", "StrongPassword123!"),
    ],
)
def test_login_rejects_invalid_credentials(
    client,
    db_session,
    email,
    password,
):
    db_session.add(
        User(
            email="login@example.com",
            password_hash=hash_password("StrongPassword123!"),
        )
    )
    db_session.commit()

    response = client.post(
        "/api/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_me_returns_current_user(authenticated_client, test_user):
    response = authenticated_client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json() == {
        "id": test_user.id,
        "email": test_user.email,
    }


def test_get_conversations_returns_only_users_conversations(
    authenticated_client,
    db_session,
    test_user,
):

    own_conversation = Conversation(
        user_id=test_user.id,
        title="My conversation",
    )

    other_user = User(
        email="other@example.com",
        password_hash="unused",
    )
    db_session.add(other_user)
    db_session.commit()
    db_session.refresh(other_user)

    foreign_conversation = Conversation(
        user_id=other_user.id,
        title="Foreign conversation",
    )

    db_session.add_all([own_conversation, foreign_conversation])
    db_session.commit()
    db_session.refresh(own_conversation)

    response = authenticated_client.get("/api/conversations")

    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == own_conversation.id
    assert data[0]["title"] == "My conversation"


def test_delete_own_conversation(
    authenticated_client,
    db_session,
    test_user,
):

    conversation = Conversation(
        user_id=test_user.id,
        title="To delete",
    )
    db_session.add(conversation)
    db_session.commit()
    db_session.refresh(conversation)

    conversation_id = conversation.id

    response = authenticated_client.delete(f"/api/conversations/{conversation_id}")

    assert response.status_code == 204

    deleted = db_session.query(Conversation).filter_by(id=conversation_id).first()

    assert deleted is None


def test_rename_conversation_strips_whitespace(
    authenticated_client,
    db_session,
    test_user,
):

    conversation = Conversation(
        user_id=test_user.id,
        title="Old title",
    )
    db_session.add(conversation)
    db_session.commit()
    db_session.refresh(conversation)

    response = authenticated_client.patch(
        f"/api/conversations/{conversation.id}",
        json={"title": "  New title  "},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "New title"

    db_session.refresh(conversation)
    assert conversation.title == "New title"


def test_rename_conversation_rejects_whitespace_only_title(
    authenticated_client,
    db_session,
    test_user,
):

    conversation = Conversation(
        user_id=test_user.id,
        title="Original title",
    )
    db_session.add(conversation)
    db_session.commit()
    db_session.refresh(conversation)

    response = authenticated_client.patch(
        f"/api/conversations/{conversation.id}",
        json={"title": "   "},
    )

    assert response.status_code == 400

    db_session.refresh(conversation)
    assert conversation.title == "Original title"


@pytest.mark.parametrize(
    "method",
    ["get", "delete", "patch"],
)
def test_conversation_operations_return_404_for_missing_id(
    authenticated_client,
    method,
):
    conversation_id = 999999

    if method == "get":
        response = authenticated_client.get(
            f"/api/conversations/{conversation_id}/messages"
        )
    elif method == "delete":
        response = authenticated_client.delete(f"/api/conversations/{conversation_id}")
    else:
        response = authenticated_client.patch(
            f"/api/conversations/{conversation_id}",
            json={"title": "New title"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"


def test_chat_returns_404_for_missing_conversation(
    authenticated_client,
    monkeypatch,
):
    def fail_if_called(*args, **kwargs):
        pytest.fail("Agent must not run for a missing conversation")

    monkeypatch.setattr(server.harness, "run", fail_if_called)

    response = authenticated_client.post(
        "/api/chat",
        json={
            "message": "Continue conversation",
            "conversation_id": 999999,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"


def test_get_messages_returns_messages(authenticated_client, db_session, test_user):
    conversation = Conversation(
        user_id=test_user.id,
        title="Test conversation",
    )
    db_session.add(conversation)
    db_session.flush()

    db_session.add_all(
        [
            Message(
                conversation_id=conversation.id,
                role="user",
                content="Привет",
            ),
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content="Привет! Чем помочь?",
            ),
        ]
    )
    db_session.commit()

    response = authenticated_client.get(
        f"/api/conversations/{conversation.id}/messages"
    )

    assert response.status_code == 200
    assert response.json() == [
        {"role": "user", "content": "Привет", "tool_trace": []},
        {
            "role": "assistant",
            "content": "Привет! Чем помочь?",
            "tool_trace": [],
        },
    ]
