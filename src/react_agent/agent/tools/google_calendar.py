import json
from datetime import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from react_agent.integrations.credentials import get_credentials, save_credentials

CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def _get_calendar_service(*, db: Session, user_id: int):
    token_data = get_credentials(
        db,
        user_id=user_id,
        provider="google_calendar",
    )

    if token_data is None:
        raise RuntimeError(
            "Google Calendar is not connected. Connect it in your account settings."
        )

    credentials = Credentials.from_authorized_user_info(
        token_data,
        CALENDAR_SCOPES,
    )

    if not credentials.valid:
        if credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
            except Exception as error:
                raise RuntimeError(
                    "Google Calendar authorization expired or could not be refreshed. "
                    "Reconnect Google Calendar."
                ) from error

            save_credentials(
                db,
                user_id=user_id,
                provider="google_calendar",
                credentials=json.loads(credentials.to_json()),
            )
        else:
            raise RuntimeError(
                "Google Calendar authorization cannot be refreshed. "
                "Reconnect Google Calendar."
            )

    return build(
        "calendar",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )


def calendar_list_events(
    time_min: str,
    time_max: str,
    max_results: int = 10,
    *,
    db: Session,
    user_id: int,
) -> str:
    """List the current user's Google Calendar events in an ISO 8601 time range."""

    try:
        start = datetime.fromisoformat(time_min.replace("Z", "+00:00"))
        end = datetime.fromisoformat(time_max.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Dates must use ISO 8601 format") from error

    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("Dates must include a timezone or UTC offset")

    if start >= end:
        raise ValueError("time_min must be earlier than time_max")

    if (end - start).total_seconds() > 31 * 24 * 60 * 60:
        raise ValueError("Time range must not exceed 31 days")

    if not 1 <= max_results <= 50:
        raise ValueError("max_results must be between 1 and 50")

    service = _get_calendar_service(db=db, user_id=user_id)

    response = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = [
        {
            "id": event.get("id"),
            "summary": event.get("summary", "(без названия)"),
            "start": event.get("start", {}),
            "end": event.get("end", {}),
            "status": event.get("status"),
        }
        for event in response.get("items", [])
    ]

    return json.dumps(
        {
            "events": events,
            "next_page_token": response.get("nextPageToken"),
        },
        ensure_ascii=False,
    )
