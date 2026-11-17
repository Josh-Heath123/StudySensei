"""GET /ai/status: keys reported as yes/no only, roles in order, today's usage per user."""

from typing import Any

import pytest
from httpx import AsyncClient
from pydantic import SecretStr

from app.api import ai as ai_router
from app.core.config import Settings, get_settings

SECRET = "super-secret-gemini-key"


def model(body: dict[str, Any], key: str) -> dict[str, Any]:
    return next(m for m in body["models"] if f"{m['provider']}/{m['model']}" == key)


async def test_with_no_keys_ai_is_unavailable(alice_api: AsyncClient) -> None:
    response = await alice_api.get("/ai/status")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert {p["name"]: p["key_set"] for p in body["providers"]} == {
        "gemini": False,
        "groq": False,
        "ollama": False,
    }
    assert body["roles"]["smart"][0] == "gemini/gemini-3.8-flash"
    assert body["roles"]["bulk"][0] == "gemini/gemini-3.5-flash-lite"
    flash = model(body, "gemini/gemini-3.8-flash")
    assert (flash["configured"], flash["used_today"], flash["daily_budget"]) == (False, 0, 18)
    assert flash["resets_at"] is not None


@pytest.fixture
def gemini_key(monkeypatch: pytest.MonkeyPatch) -> Settings:
    settings = get_settings().model_copy(update={"gemini_api_key": SecretStr(SECRET)})
    monkeypatch.setattr(ai_router, "get_settings", lambda: settings)
    return settings


async def test_a_set_key_is_yes_and_never_shown(
    gemini_key: Settings, alice_api: AsyncClient
) -> None:
    response = await alice_api.get("/ai/status")

    body = response.json()
    assert body["available"] is True
    assert {p["name"]: p["key_set"] for p in body["providers"]}["gemini"] is True
    assert model(body, "gemini/gemini-3.8-flash")["configured"] is True
    assert model(body, "groq/openai/gpt-oss-120b")["configured"] is False
    assert SECRET not in response.text
