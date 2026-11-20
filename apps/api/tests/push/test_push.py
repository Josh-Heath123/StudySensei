"""Web Push (decision 0024): the keys CLI, the payload, send outcomes with the fake sender,
and queueing reminders. Nothing here reaches the network (``fake_push`` in conftest)."""

import builtins
import logging
import uuid
from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from py_vapid import Vapid02
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    PushSubscription,
    User,
)
from app.push import keys
from app.services.push.payload import reminder_payload, slot_key
from app.services.push.sender import FakePushSender, get_sender
from app.services.push.subscriptions import send_to_user, upsert
from tests.planning.test_replan import NOW

SAST = ZoneInfo("Africa/Johannesburg")


# --- keys -------------------------------------------------------------------------------


def test_the_keys_cli_prints_three_lines_and_writes_nothing(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_files(*args: object, **kwargs: object) -> object:
        raise AssertionError("the keys CLI must not open files")

    monkeypatch.setattr(builtins, "open", no_files)
    keys.main()
    out = capsys.readouterr().out.splitlines()
    settings = [line for line in out if not line.startswith("#")]
    assert [line.split("=", 1)[0] for line in settings] == [
        "VAPID_PUBLIC_KEY",
        "VAPID_PRIVATE_KEY",
        "VAPID_SUBJECT",
    ]
    public, private = settings[0].split("=", 1)[1], settings[1].split("=", 1)[1]
    assert len(public) == 87 and public.startswith("B")  # 65 bytes: 0x04 then x and y
    assert len(private) == 43  # 32 bytes
    assert settings[2].startswith("VAPID_SUBJECT=mailto:")
    # The private key loads the way the sender loads it.
    Vapid02.from_string(private)


def test_new_keys_are_different_each_time() -> None:
    assert keys.new_keys() != keys.new_keys()


def test_with_keys_the_configured_sender_is_used(push_on: FakePushSender) -> None:
    assert get_sender() is push_on


def test_no_keys_no_sender() -> None:
    assert get_sender() is None


# --- payload ----------------------------------------------------------------------------


def test_payload_for_a_topic_and_a_review() -> None:
    start = NOW.replace(hour=18)
    study = reminder_payload(
        topic_name="Ch1 Overview",
        assessment_name="COS330 Exam",
        start=start,
        minutes=50,
        method_text="Read the linked pages and make short notes.",
        timezone=SAST,
        tag="k",
    )
    assert study == {
        "title": "Ch1 Overview at 18:00",
        "body": "50 min · Read the linked pages and make short notes.",
        "url": "/",
        "tag": "k",
    }
    review = reminder_payload(
        topic_name=None,
        assessment_name="COS330 Exam",
        start=start,
        minutes=50,
        method_text="Mix every topic.",
        timezone=SAST,
        tag="k",
    )
    assert review["title"] == "Final review: COS330 Exam at 18:00"


def test_slot_key_ignores_the_offset_and_changes_with_the_slot() -> None:
    a, t = uuid.uuid4(), uuid.uuid4()
    start = NOW.replace(hour=18)
    end = start + timedelta(minutes=50)
    key = slot_key(start, end, a, t)
    assert len(key) == 64
    assert key == slot_key(start.astimezone(ZoneInfo("UTC")), end, a, t)
    assert key != slot_key(start + timedelta(minutes=5), end + timedelta(minutes=5), a, t)
    assert key != slot_key(start, end, a, None)


# --- send outcomes ----------------------------------------------------------------------


async def subscribe(session: AsyncSession, user: User, name: str = "a") -> PushSubscription:
    row, created = await upsert(
        session,
        user_id=user.id,
        endpoint=f"https://push.example/{name}",
        p256dh="BKey",
        auth="Auth",
        label=f"Edge on Windows ({name})",
    )
    assert created
    return row


async def test_upsert_by_endpoint_refreshes_keys(session: AsyncSession, user_a: User) -> None:
    first = await subscribe(session, user_a)
    again, created = await upsert(
        session,
        user_id=user_a.id,
        endpoint=first.endpoint,
        p256dh="BNew",
        auth="New",
        label="Edge on Windows",
    )
    assert not created and again.id == first.id
    assert (again.p256dh, again.auth, again.label) == ("BNew", "New", "Edge on Windows")


async def test_a_success_resets_failures(
    session: AsyncSession, user_a: User, push_on: FakePushSender
) -> None:
    row = await subscribe(session, user_a)
    row.failures = 3
    await session.commit()
    out = await send_to_user(
        session, push_on, user_id=user_a.id, payload={"title": "x"}, ttl=60, now=NOW
    )
    assert [o.outcome for o in out] == ["sent"]
    await session.refresh(row)
    assert (row.failures, row.last_success_at) == (0, NOW)
    assert push_on.sent[0][1:] == ({"title": "x"}, 60)


@pytest.mark.parametrize("status", [404, 410])
async def test_gone_deletes_the_subscription(
    session: AsyncSession, user_a: User, push_on: FakePushSender, status: int
) -> None:
    row = await subscribe(session, user_a)
    push_on.statuses[row.endpoint] = status
    out = await send_to_user(session, push_on, user_id=user_a.id, payload={}, ttl=60, now=NOW)
    assert [o.outcome for o in out] == ["removed"]
    assert await session.scalar(select(func.count()).select_from(PushSubscription)) == 0


async def test_five_failures_in_a_row_delete_it_and_logs_never_name_the_endpoint(
    session: AsyncSession,
    user_a: User,
    push_on: FakePushSender,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = await subscribe(session, user_a)
    endpoint, row_id = row.endpoint, row.id
    push_on.statuses[endpoint] = None  # unreachable
    # Alembic's fileConfig (the migrated_db fixture) disables loggers that already exist.
    monkeypatch.setattr(logging.getLogger("studysensei.push"), "disabled", False)
    caplog.set_level(logging.INFO)
    outcomes = []
    for _ in range(5):
        out = await send_to_user(session, push_on, user_id=user_a.id, payload={}, ttl=60, now=NOW)
        outcomes += [o.outcome for o in out]
    assert outcomes == ["failed"] * 4 + ["removed"]
    assert await session.get(PushSubscription, row_id) is None
    assert str(row_id) in caplog.text
    assert endpoint not in caplog.text and "push.example" not in caplog.text
