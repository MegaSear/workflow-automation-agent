import json
import logging
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from react_agent.backend.auth.auth import (
    get_current_user,
)
from react_agent.backend.config import settings
from react_agent.backend.db.database import get_db
from react_agent.backend.db.models import User
from react_agent.backend.integrations.credentials import (
    ALLOWED_PROVIDERS,
    delete_credentials,
    get_credentials,
    save_credentials,
)
from react_agent.backend.integrations.github import validate_github_token
from react_agent.backend.integrations.google_oauth import create_google_flow
from react_agent.backend.integrations.jira import validate_jira_credentials
from react_agent.backend.integrations.oauth_state import (
    consume_google_oauth_state,
    save_google_oauth_state,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

router = APIRouter(
    prefix="/api/integrations",
    tags=["Integrations"],
)


class JiraCredentialsRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    api_token: str = Field(min_length=1, max_length=1000)


class GitHubCredentialsRequest(BaseModel):
    token: str = Field(min_length=1, max_length=1000)


@router.get("/")
def list_integrations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {
        provider: get_credentials(db, user_id=user.id, provider=provider) is not None
        for provider in sorted(ALLOWED_PROVIDERS)
    }


@router.put("/jira")
async def connect_jira(
    request: JiraCredentialsRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    credentials = request.model_dump()
    try:
        valid = await validate_jira_credentials(credentials)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Jira credentials were rejected",
        )
    try:
        save_credentials(
            db,
            user_id=user.id,
            provider="jira",
            credentials=credentials,
        )
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Integration credential storage is unavailable",
        ) from error
    return {"connected": True}


@router.put("/github")
def connect_github(
    request: GitHubCredentialsRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        valid = validate_github_token(request.token)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="GitHub token was rejected",
        )
    try:
        save_credentials(
            db,
            user_id=user.id,
            provider="github",
            credentials={"token": request.token},
        )
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Integration credential storage is unavailable",
        ) from error
    return {"connected": True}


@router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_integration(
    provider: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if provider not in ALLOWED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )
    delete_credentials(db, user_id=user.id, provider=provider)


@router.get("/google_calendar/auth-url")
def google_calendar_auth_url(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    nonce = secrets.token_urlsafe(24)
    state = jwt.encode(
        {
            "sub": str(user.id),
            "purpose": "google_calendar_oauth",
            "nonce": nonce,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    try:
        flow = create_google_flow(state=state)
        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        save_google_oauth_state(
            db,
            nonce=nonce,
            user_id=user.id,
            code_verifier=flow.code_verifier,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
    except (OSError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Calendar OAuth is not configured",
        ) from error
    return {"authorization_url": authorization_url}


@router.get("/google_calendar/callback")
def google_calendar_callback(
    code: str | None = None,
    state: str = "",
    error: str | None = None,
    db: Session = Depends(get_db),
):
    if error or not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Calendar authorization was not completed",
        )
    try:
        payload = jwt.decode(
            state,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={
                "require": ["exp", "sub", "nonce", "purpose"],
            },
        )
    except jwt.PyJWTError as exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state",
        ) from exception

    if payload.get("purpose") != "google_calendar_oauth":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state",
        )
    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id.isdecimal():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state",
        )
    if db.get(User, int(user_id)) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    nonce = payload.get("nonce")
    if not isinstance(nonce, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state",
        )

    code_verifier = consume_google_oauth_state(
        db,
        nonce=nonce,
        user_id=int(user_id),
    )

    if code_verifier is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth session expired or already used",
        )
    try:
        flow = create_google_flow(
            state=state,
            code_verifier=code_verifier,
            autogenerate_code_verifier=False,
        )
        flow.fetch_token(code=code)
        credentials = json.loads(flow.credentials.to_json())
        save_credentials(
            db,
            user_id=int(user_id),
            provider="google_calendar",
            credentials=credentials,
        )
    except Exception as exception:
        logger.exception("Google Calendar OAuth callback failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not complete Google Calendar authorization",
        ) from exception

    return RedirectResponse(
        url=f"{settings.FRONTEND_URL}/?integration=google_calendar",
        status_code=status.HTTP_303_SEE_OTHER,
    )
