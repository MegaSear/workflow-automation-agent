import json
import os
from urllib.parse import urlsplit

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from sqlalchemy.orm import Session

from react_agent.backend.config import settings
from react_agent.backend.integrations.credentials import (
    get_credentials,
    save_credentials,
)

GOOGLE_CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events.readonly",
]


def get_google_calendar_access_token(db: Session, *, user_id: int) -> str:
    credential_info = get_credentials(
        db,
        user_id=user_id,
        provider="google_calendar",
    )
    if credential_info is None:
        raise RuntimeError("Google Calendar is not connected for this user")

    credentials = Credentials.from_authorized_user_info(
        credential_info,
        scopes=GOOGLE_CALENDAR_SCOPES,
    )
    if not credentials.valid:
        if not credentials.refresh_token:
            raise RuntimeError("Google Calendar authorization must be renewed")
        credentials.refresh(Request())
        save_credentials(
            db,
            user_id=user_id,
            provider="google_calendar",
            credentials=json.loads(credentials.to_json()),
        )
    if not credentials.token:
        raise RuntimeError("Google Calendar did not provide an access token")
    return credentials.token


def create_google_flow(
    *,
    state: str | None = None,
    code_verifier: str | None = None,
    autogenerate_code_verifier: bool = True,
) -> Flow:
    redirect_uri = settings.GOOGLE_CALENDAR_REDIRECT_URI
    parsed_redirect = urlsplit(redirect_uri)
    if parsed_redirect.scheme == "http" and parsed_redirect.hostname in {
        "localhost",
        "127.0.0.1",
    }:
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

    flow = Flow.from_client_secrets_file(
        str(settings.GOOGLE_CALENDAR_CREDENTIALS_FILE),
        scopes=GOOGLE_CALENDAR_SCOPES,
        state=state,
        code_verifier=code_verifier,
        autogenerate_code_verifier=autogenerate_code_verifier,
    )
    flow.redirect_uri = redirect_uri
    return flow
