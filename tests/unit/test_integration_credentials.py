from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from react_agent.config import settings
from react_agent.db.models import Base, User, UserIntegration
from react_agent.integrations.credentials import (
    delete_credentials,
    get_credentials,
    save_credentials,
)


def test_credentials_are_encrypted_and_user_scoped(monkeypatch):
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(settings, "INTEGRATION_ENCRYPTION_KEY", key)

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        db.add_all(
            [
                User(id=1, email="one@example.com", password_hash="hash1"),
                User(id=2, email="two@example.com", password_hash="hash2"),
            ]
        )
        db.commit()

        credentials = {
            "base_url": "https://example.atlassian.net",
            "email": "one@example.com",
            "api_token": "secret-token",
        }

        save_credentials(
            db,
            user_id=1,
            provider="jira",
            credentials=credentials,
        )

        record = db.query(UserIntegration).one()

        assert "secret-token" not in record.credentials_encrypted
        assert get_credentials(db, user_id=1, provider="jira") == credentials
        assert get_credentials(db, user_id=2, provider="jira") is None

        assert delete_credentials(db, user_id=1, provider="jira")
        assert get_credentials(db, user_id=1, provider="jira") is None

    engine.dispose()
