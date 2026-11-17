"""Providers and roles, read from settings (decision 0002).

A *route* is one provider + model. Each role (smart, bulk) is an ordered list of
routes kept in config, so swapping a model never needs a code change. Routes on a
provider without a key are listed but not ``configured``, and the client skips them.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import SecretStr

from app.core.config import ReasoningEffort, RouteSetting, Settings

AIRole = Literal["smart", "bulk", "vision", "long"]
ROLES: tuple[AIRole, ...] = ("smart", "bulk", "vision", "long")
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
    # From config; None means the model's own default. ``effort_to_send`` says what is sent.
    reasoning_effort: ReasoningEffort | None = None
    # The levels this model accepts, lowest first; empty means it is never sent one.
    supported_efforts: tuple[ReasoningEffort, ...] = ()

    def effort_to_send(self, override: ReasoningEffort | None = None) -> ReasoningEffort | None:
        """The ``reasoning_effort`` for a request: the call's override, else the route's."""
        return wire_effort(self.supported_efforts, override or self.reasoning_effort)

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


EFFORT_ORDER: tuple[ReasoningEffort, ...] = ("minimal", "low", "medium", "high")


def wire_effort(
    supported: Sequence[ReasoningEffort], effort: ReasoningEffort | None
) -> ReasoningEffort | None:
    """The ``reasoning_effort`` to send, or None to leave it out.

    A level the model lacks is raised to its lowest supported level at or above it (so
    "minimal" goes to Gemini 3.8 Flash as "low"); above its highest, it gets its highest.
    """
    if effort is None or not supported:
        return None
    ranked = sorted(supported, key=EFFORT_ORDER.index)
    wanted = EFFORT_ORDER.index(effort)
    return next((level for level in ranked if EFFORT_ORDER.index(level) >= wanted), ranked[-1])


def role_settings(role: AIRole, settings: Settings) -> list[RouteSetting]:
    return {
        "smart": settings.ai_smart,
        "bulk": settings.ai_bulk,
        "vision": settings.ai_vision,
        "long": settings.ai_long,
    }[role]


def routes_for(role: AIRole, settings: Settings) -> list[Route]:
    """Every route in the role, in order, configured or not.

    Ollama (when set) goes last in the text roles, but not in ``vision``.
    """
    by_name = providers(settings)
    entries = list(role_settings(role, settings))
    if settings.ollama_model is not None and role != "vision":
        entries.append(RouteSetting(route=f"ollama/{settings.ollama_model}"))
    vision = {entry.route for entry in settings.ai_vision}
    routes = []
    for entry in entries:
        provider, model = parse_route_key(entry.route)
        routes.append(
            Route(
                by_name[provider],
                model,
                settings.ai_daily_budget.get(entry.route),
                entry.route in vision,
                entry.reasoning_effort,
                tuple(settings.ai_reasoning_efforts.get(entry.route, ())),
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
