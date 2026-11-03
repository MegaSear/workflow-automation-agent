from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from react_agent.backend.db.models import GoogleOAuthState
from react_agent.backend.integrations.credentials import _fernet


def save_google_oauth_state(
    db: Session,
    *,
    nonce: str,
    user_id: int,
    code_verifier: str,
    expires_at: datetime,
) -> None:
    encrypted = _fernet().encrypt(code_verifier.encode("utf-8")).decode("ascii")

    db.execute(
        delete(GoogleOAuthState).where(
            GoogleOAuthState.expires_at <= datetime.now(timezone.utc)
        )
    )

    db.add(
        GoogleOAuthState(
            nonce=nonce,
            user_id=user_id,
            code_verifier_encrypted=encrypted,
            expires_at=expires_at,
        )
    )
    db.commit()


def consume_google_oauth_state(
    db: Session,
    *,
    nonce: str,
    user_id: int,
) -> str | None:
    record = db.scalar(
        select(GoogleOAuthState).where(
            GoogleOAuthState.nonce == nonce,
            GoogleOAuthState.user_id == user_id,
        )
    )

    if record is None:
        return None

    if record.expires_at <= datetime.now(timezone.utc):
        db.delete(record)
        db.commit()
        return None

    code_verifier = (
        _fernet()
        .decrypt(record.code_verifier_encrypted.encode("ascii"))
        .decode("utf-8")
    )

    # Состояние одноразовое: удаляем до обмена authorization code.
    db.delete(record)
    db.commit()

    return code_verifier
