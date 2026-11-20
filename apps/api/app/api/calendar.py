"""The plan as a calendar: a private subscribable link, and a download (decision 0024).

``GET /calendar/{token}.ics`` has no CurrentUser: the token *is* the credential, looked up by
its hash, and it serves only that user's plan. It must stay outside any future auth
middleware (ADR 0024), or calendar apps, which can't sign in, would lose the feed.
"""

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser
from app.core import clock
from app.core.config import get_settings
from app.core.db import SessionDep
from app.schemas.push import CalendarFeedCreatedOut, CalendarFeedOut
from app.services.calendar import feed

router = APIRouter(tags=["calendar"])

ICS = "text/calendar; charset=utf-8"
ICS_HEADERS = {"Cache-Control": "private, max-age=300"}


def _url(token: str) -> str:
    # Through the web app's origin: in dev Vite proxies /api to the API.
    return f"{get_settings().public_url.rstrip('/')}/api/calendar/{token}.ics"


@router.post(
    "/calendar/feed", response_model=CalendarFeedCreatedOut, status_code=status.HTTP_201_CREATED
)
async def create_feed(session: SessionDep, user: CurrentUser) -> CalendarFeedCreatedOut:
    """Create the private calendar link, or reset it (the old link stops working). The URL is
    returned this once."""
    token, row = await feed.create_or_reset(session, user_id=user.id, now=clock.now())
    return CalendarFeedCreatedOut(url=_url(token), created_at=row.created_at)


@router.get("/calendar/feed", response_model=CalendarFeedOut)
async def get_feed(session: SessionDep, user: CurrentUser) -> CalendarFeedOut:
    """Whether the link exists, when it was made and last fetched. Never the token."""
    row = await feed.get_feed(session, user_id=user.id)
    return CalendarFeedOut(
        exists=row is not None,
        created_at=row.created_at if row else None,
        last_fetched_at=row.last_fetched_at if row else None,
    )


@router.delete("/calendar/feed", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feed(session: SessionDep, user: CurrentUser) -> None:
    await feed.delete_feed(session, user_id=user.id)


# Declared before /calendar/{token}.ics, so "plan" isn't taken for a token.
@router.get(
    "/calendar/plan.ics",
    response_class=Response,
    responses={200: {"content": {"text/calendar": {}}}},
)
async def download_plan(session: SessionDep, user: CurrentUser) -> Response:
    """Your plan as an .ics file, for the Download button."""
    body = await feed.calendar_file(session, user_id=user.id, now=clock.now())
    return Response(
        body,
        media_type=ICS,
        headers={**ICS_HEADERS, "Content-Disposition": 'attachment; filename="studysensei.ics"'},
    )


@router.get(
    "/calendar/{token}.ics",
    response_class=Response,
    responses={200: {"content": {"text/calendar": {}}}, 404: {}},
)
async def subscribed_plan(token: str, session: SessionDep) -> Response:
    """The plan of the user this link belongs to (no sign-in: the token is the key)."""
    now = clock.now()
    user_id = await feed.user_for_token(session, token, now=now)
    body = await feed.calendar_file(session, user_id=user_id, now=now)
    return Response(body, media_type=ICS, headers=ICS_HEADERS)
