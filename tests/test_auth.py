"""Tests for authentication and password security.

Covers:
- JWT authentication and user lookup.
- Rejection of expired tokens and missing required claims.
- Handling of invalid JWT claims, signatures, and missing users.
- Password hashing and password verification.

The database is mocked to isolate authentication logic from database access.
"""

from unittest.mock import Mock

import jwt
import pytest
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from datetime import datetime, timedelta, timezone

from react_agent.db.models import User
from react_agent.auth.auth import (
    create_access_token, get_current_user,
    hash_password, verify_password,
)
from react_agent.config import settings


USER_IDS = [1, 2, 3]
UNKNOWN_USER_ID = 999

@pytest.fixture
def users():
    return [
        Mock(spec=User, id=user_id) 
        for user_id in USER_IDS
    ]

@pytest.fixture
def db(users):
    db = Mock()
    users_by_id = {user.id: user for user in users}
    db.get.side_effect = lambda _, user_id: users_by_id.get(user_id)
    return db

def create_credentials(user_id: int):
    return HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=create_access_token(user_id),
    )


@pytest.mark.parametrize("user_id", USER_IDS)
def test_get_current_user_returns_correct_user(user_id, users, db):
    """ 
    Проверка на сценарий: возвращается правильный юзер
    """

    result = get_current_user(
        credentials=create_credentials(user_id),
        db=db,
    )

    expected_user = next(user for user in users if user.id == user_id)

    assert result is expected_user                # Тот ли объект юзера возвращается
    db.get.assert_called_once_with(User, user_id) # Внутри функции get_current_user вызывается db.get с корректными аргументами


def test_get_current_user_raises_401_if_user_not_found(db):
    """
    Проверка на сценарий: пользователь не найден
    """

    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=create_access_token(UNKNOWN_USER_ID),
    )

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(credentials=credentials, db=db)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == "User not found"
    db.get.assert_called_once_with(User, UNKNOWN_USER_ID)


def test_get_current_user_rejects_token_without_sub(db):
    """
    Проверка на сценарий: токен без sub
    """
    token = jwt.encode(
        {
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=token,
    )

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(credentials=credentials, db=db)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == "Invalid token"
    db.get.assert_not_called()

def test_get_current_user_rejects_expired_token(db):
    """
    Проверка на сценарий: истекший токен
    """
    token = jwt.encode(
        {
            "sub": "1",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=token,
    )

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(credentials=credentials, db=db)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == "Invalid or expired token"
    db.get.assert_not_called()

@pytest.mark.parametrize(
    "sub",
    ["abc", "", "1.5", "0", "-1"],
)
def test_get_current_user_rejects_invalid_sub(sub, db):
    """
    Проверка на сценарий: невалидная sub
    """
    token = jwt.encode(
        {
            "sub": sub,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=token,
    )

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(credentials=credentials, db=db)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == "Invalid token"
    db.get.assert_not_called()


def test_get_current_user_rejects_invalid_signature(db):
    """
    Проверка на сценарий: невалидная подпись
    """
    jwt_secret_key = "completely-different-secret-key-123"
    token = jwt.encode(
        {
            "sub": "1",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        jwt_secret_key,
        algorithm=settings.JWT_ALGORITHM,
    )

    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=token,
    )

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(credentials=credentials, db=db)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == "Invalid or expired token"
    db.get.assert_not_called()

def test_get_current_user_rejects_token_without_exp(db):
    """
    Проверка на сценарий: токен без обязательного exp.
    """
    token = jwt.encode(
        {
            "sub": "1",
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=token,
    )

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(credentials=credentials, db=db)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == "Invalid or expired token"
    db.get.assert_not_called()


def test_hash_password_does_not_store_plaintext():
    password = "my-test-password-key-123"
    hashed_password = hash_password(password)
    assert hashed_password != password
    assert verify_password(password, hashed_password)


def test_verify_password_rejects_wrong_password():
    password = "my-test-password-key-123"
    hashed_password = hash_password(password)
    assert not verify_password("wrong-password", hashed_password)