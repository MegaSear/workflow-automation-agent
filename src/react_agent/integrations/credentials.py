import json

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from react_agent.config import settings
from react_agent.db.models import UserIntegration

ALLOWED_PROVIDERS = {"jira", "google_calendar"}


def _fernet() -> Fernet:
    key = settings.INTEGRATION_ENCRYPTION_KEY

    if not key:
        raise RuntimeError("INTEGRATION_ENCRYPTION_KEY is required to use integrations")

    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as error:
        raise RuntimeError("INTEGRATION_ENCRYPTION_KEY is invalid") from error


def save_credentials(
    db: Session,
    *,
    user_id: int,
    provider: str,
    credentials: dict,
) -> None:
    if provider not in ALLOWED_PROVIDERS:
        raise ValueError("Unsupported integration provider")

    if not isinstance(credentials, dict):
        raise ValueError("Credentials must be a JSON object")

    encrypted = (
        _fernet().encrypt(json.dumps(credentials).encode("utf-8")).decode("ascii")
    )

    record = db.scalar(
        select(UserIntegration).where(
            UserIntegration.user_id == user_id,
            UserIntegration.provider == provider,
        )
    )

    if record is None:
        record = UserIntegration(
            user_id=user_id,
            provider=provider,
            credentials_encrypted=encrypted,
        )
        db.add(record)
    else:
        record.credentials_encrypted = encrypted

    db.commit()


def get_credentials(
    db: Session,
    *,
    user_id: int,
    provider: str,
) -> dict | None:
    if provider not in ALLOWED_PROVIDERS:
        raise ValueError("Unsupported integration provider")

    record = db.scalar(
        select(UserIntegration).where(
            UserIntegration.user_id == user_id,
            UserIntegration.provider == provider,
        )
    )

    if record is None:
        return None

    try:
        decrypted = _fernet().decrypt(record.credentials_encrypted.encode("ascii"))
        credentials = json.loads(decrypted)
    except (InvalidToken, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError(
            "Stored integration credentials cannot be decrypted"
        ) from error

    if not isinstance(credentials, dict):
        raise RuntimeError("Stored integration credentials have invalid format")

    return credentials


def delete_credentials(
    db: Session,
    *,
    user_id: int,
    provider: str,
) -> bool:
    if provider not in ALLOWED_PROVIDERS:
        raise ValueError("Unsupported integration provider")

    record = db.scalar(
        select(UserIntegration).where(
            UserIntegration.user_id == user_id,
            UserIntegration.provider == provider,
        )
    )

    if record is None:
        return False

    db.delete(record)
    db.commit()
    return True
