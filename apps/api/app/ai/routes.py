"""Providers and roles, read from settings (decision 0002).

A *route* is one provider + model. Each role (smart, bulk) is an ordered list of
routes kept in config, so swapping a model never needs a code change. Routes on a
provider without a key are listed but not ``configured``, and the client skips them.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import SecretStr

from app.core.config import Settings

AIRole = Literal["smart", "bulk"]
ROLES: tuple[AIRole, ...] = ("smart", "bulk")
PROVIDERS = ("gemini", "groq", "ollama")


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    # Never logged or returned; only whether it is set.
    api_key: SecretStr | None
    configured: bool


@dataclass(frozen=True)
class Route:
    provider: Provider
    model: str
    # Requests per day this client allows itself, or None for no limit (Ollama).
    daily_budget: int | None
    vision: bool

    @property
    def key(self) -> str:
        return f"{self.provider.name}/{self.model}"

    @property
    def configured(self) -> bool:
        return self.provider.configured


def providers(settings: Settings) -> dict[str, Provider]:
    return {
        "gemini": Provider(
            "gemini",
            settings.gemini_base_url,
            settings.gemini_api_key,
            settings.gemini_api_key is not None,
        ),
        "groq": Provider(
            "groq",
            settings.groq_base_url,
            settings.groq_api_key,
            settings.groq_api_key is not None,
        ),
        "ollama": Provider(
            "ollama", settings.ollama_base_url, None, settings.ollama_model is not None
        ),
    }


def parse_route_key(key: str) -> tuple[str, str]:
    """``"groq/openai/gpt-oss-120b"`` → ``("groq", "openai/gpt-oss-120b")``."""
    provider, sep, model = key.partition("/")
    if not sep or not model or provider not in PROVIDERS:
        raise ValueError(f"AI route {key!r} must be 'provider/model' with provider in {PROVIDERS}")
    return provider, model


def routes_for(role: AIRole, settings: Settings) -> list[Route]:
    """Every route in the role, in order, configured or not. Ollama (when set) goes last."""
    by_name = providers(settings)
    keys = list(settings.ai_smart if role == "smart" else settings.ai_bulk)
    if settings.ollama_model is not None:
        keys.append(f"ollama/{settings.ollama_model}")
    routes = []
    for key in keys:
        provider, model = parse_route_key(key)
        routes.append(
            Route(
                by_name[provider],
                model,
                settings.ai_daily_budget.get(key),
                key in settings.ai_vision_models,
            )
        )
    return routes


def all_routes(settings: Settings) -> list[Route]:
    """Each distinct route across the roles, in role order."""
    seen: dict[str, Route] = {}
    for role in ROLES:
        for route in routes_for(role, settings):
            seen.setdefault(route.key, route)
    return list(seen.values())
