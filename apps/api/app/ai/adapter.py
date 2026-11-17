"""The one OpenAI-compatible adapter, used for every provider (decision 0002).

It sends ``POST {base_url}/chat/completions`` and ``GET {base_url}/models`` with httpx.
It knows nothing about roles, budgets or fallback; the client does.
Error messages never include the key or the prompt.
"""

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.ai.messages import Message, to_wire
from app.ai.routes import Provider

# Gemini puts the wait in the error body ("retryDelay": "37s") rather than a header.
_RETRY_DELAY = re.compile(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"')


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int
    output_tokens: int


class ProviderError(Exception):
    """A failed request. ``retryable`` for 429, 5xx, timeouts and lost connections."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None,
        retry_after: float | None,
        timed_out: bool = False,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after
        self.timed_out = timed_out

    @property
    def rate_limited(self) -> bool:
        return self.status == 429

    @property
    def retryable(self) -> bool:
        return self.status is None or self.status == 429 or self.status >= 500


def retry_after_seconds(response: httpx.Response, now: datetime | None = None) -> float | None:
    """Seconds to wait from a Retry-After header (seconds or HTTP date), or Gemini's retryDelay."""
    header = response.headers.get("retry-after")
    if header:
        header = header.strip()
        try:
            return max(0.0, float(header))
        except ValueError:
            pass
        try:
            when = parsedate_to_datetime(header)
        except (TypeError, ValueError):
            when = None
        if when is not None:
            if when.tzinfo is None:
                when = when.replace(tzinfo=UTC)
            return max(0.0, (when - (now or datetime.now(UTC))).total_seconds())
    match = _RETRY_DELAY.search(response.text)
    return float(match.group(1)) if match else None


def _url(provider: Provider, path: str) -> str:
    return provider.base_url.rstrip("/") + "/" + path


def _headers(provider: Provider) -> dict[str, str]:
    if provider.api_key is None:
        return {}
    return {"Authorization": f"Bearer {provider.api_key.get_secret_value()}"}


MAX_PROVIDER_MESSAGE = 300


def provider_message(response: httpx.Response) -> str | None:
    """The ``error.message`` from an error body, trimmed; nothing else from the response.

    OpenAI-style bodies are ``{"error": {"message": ...}}``; Gemini's compatibility layer
    sometimes wraps that in a list. The request and headers are never included.
    """
    try:
        body: Any = response.json()
    except ValueError:
        return None
    if isinstance(body, list) and body:
        body = body[0]
    error = body.get("error") if isinstance(body, dict) else None
    message = error.get("message") if isinstance(error, dict) else error
    if not isinstance(message, str) or not message.strip():
        return None
    message = " ".join(message.split())
    if len(message) > MAX_PROVIDER_MESSAGE:
        message = message[: MAX_PROVIDER_MESSAGE - 1].rstrip() + "…"
    return message


def http_error(name: str, response: httpx.Response) -> str:
    """``"gemini: HTTP 400: Thinking level MINIMAL is not supported…"``."""
    message = provider_message(response)
    base = f"{name}: HTTP {response.status_code}"
    return f"{base}: {message}" if message else base


def _model_id(raw: str) -> str:
    # Gemini lists "models/gemini-…"; requests take the bare ID.
    return raw.removeprefix("models/")


class OpenAICompatAdapter:
    def __init__(self, provider: Provider, http: httpx.AsyncClient) -> None:
        self.provider = provider
        self._http = http

    async def _send(
        self, method: str, path: str, body: dict[str, Any] | None, deadline: float | None = None
    ) -> Any:
        """One request. ``deadline`` caps the whole call in seconds (connect + wait + read)."""
        name = self.provider.name
        try:
            async with asyncio.timeout(deadline):
                response = await self._http.request(
                    method, _url(self.provider, path), json=body, headers=_headers(self.provider)
                )
        except (httpx.TimeoutException, TimeoutError) as exc:
            phase = "connecting" if isinstance(exc, httpx.ConnectTimeout) else "waiting for a reply"
            raise ProviderError(
                f"{name}: timed out {phase}", status=None, retry_after=None, timed_out=True
            ) from exc
        except httpx.TransportError as exc:
            raise ProviderError(
                f"{name}: couldn't connect ({type(exc).__name__})", status=None, retry_after=None
            ) from exc
        if response.status_code >= 400:
            raise ProviderError(
                http_error(name, response),
                status=response.status_code,
                retry_after=retry_after_seconds(response),
            )
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError(f"{name}: reply wasn't JSON", status=502, retry_after=None) from exc

    async def complete(
        self,
        model: str,
        messages: list[Message],
        *,
        json_mode: bool = False,
        reasoning_effort: str | None = None,
        deadline: float | None = None,
    ) -> Completion:
        """Send ``reasoning_effort`` as given (None leaves it out): see ``routes.wire_effort``."""
        body: dict[str, Any] = {"model": model, "messages": [to_wire(m) for m in messages]}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if reasoning_effort is not None:
            body["reasoning_effort"] = reasoning_effort
        data = await self._send("POST", "chat/completions", body, deadline)
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                f"{self.provider.name}: unexpected reply shape", status=502, retry_after=None
            ) from exc
        usage = data.get("usage") or {}
        return Completion(
            text=str(text),
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
        )

    async def list_models(self, deadline: float | None = None) -> list[str]:
        data = await self._send("GET", "models", None, deadline)
        return sorted(_model_id(str(item["id"])) for item in data.get("data", []))
