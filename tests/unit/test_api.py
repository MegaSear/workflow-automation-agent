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

import pytest

from react_agent.api import server
from react_agent.api.server import app
from react_agent.auth.auth import get_current_user, hash_password
from react_agent.db.models import Conversation, Message, User

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

    def fake_run(history, user_input, *, workspace_id, user_id, db):
        assert history == []
        assert user_input == "Hello"
        assert workspace_id == test_user.id
        assert user_id == test_user.id
        assert db is not None
        return "Hello! How can I help?"

    monkeypatch.setattr(server.harness, "run", fake_run)

    response = authenticated_client.post(
        "/api/chat",
        json={"message": "Hello"},
    )

    assert response.status_code == 200

    data = response.json()
    assert data["response"] == "Hello! How can I help?"
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

    def fake_run(history, user_input, *, workspace_id, user_id, db):
        assert history == expected_history
        assert user_input == "What is my name?"
        assert workspace_id == test_user.id
        assert user_id == test_user.id
        assert db is not None
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
        {"role": "user", "content": "Привет"},
        {"role": "assistant", "content": "Привет! Чем помочь?"},
    ]
