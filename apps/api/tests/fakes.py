"""Deterministic stand-ins for the embedding model and the AI providers, so tests stay offline."""

import asyncio
import hashlib
import json
import math
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from app.services.search.embedding import DIMENSIONS

_TOKENS = re.compile(r"\w+|[^\w\s]")
_WORDS = re.compile(r"\w+")


class FakeEmbedder:
    """Bag of words hashed into 384 dimensions, normalised.

    Texts sharing words get close vectors, so vector ranking is meaningful in tests.
    Tokens are words and punctuation marks, roughly like a WordPiece tokenizer.
    """

    def __init__(self) -> None:
        self.passages: list[str] = []
        self.passage_calls: list[int] = []
        self.query_calls: list[str] = []

    def count_tokens(self, text: str) -> int:
        return len(_TOKENS.findall(text))

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * DIMENSIONS
        for word in _WORDS.findall(text.lower()):
            digest = hashlib.blake2b(word.encode(), digest_size=4).digest()
            vector[int.from_bytes(digest) % DIMENSIONS] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            vector[0], norm = 1.0, 1.0
        return [value / norm for value in vector]

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        self.passage_calls.append(len(texts))
        self.passages.extend(texts)
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        self.query_calls.append(text)
        return self._vector(text)


class FakeLLM:
    """An httpx transport standing in for every AI provider: no network in tests.

    Script replies per model with ``fake.reply("model", ok("hi"), rate_limited(5))``; each
    request takes the model's next reply. A reply can also be an exception to raise, such
    as ``httpx.ReadTimeout("slow")``, and ``slow("model", seconds)`` delays every answer.
    A request for an unscripted model fails the test.
    ``requests`` records what was sent (host, model, JSON body and headers).
    """

    def __init__(self) -> None:
        self.script: dict[str, list[httpx.Response | Exception]] = {}
        self.delays: dict[str, float] = {}
        self.hooks: dict[str, Callable[[], Awaitable[None]]] = {}
        self.requests: list[SentRequest] = []

    def reply(self, model: str, *responses: httpx.Response | Exception) -> None:
        self.script.setdefault(model, []).extend(responses)

    def slow(self, model: str, seconds: float) -> None:
        self.delays[model] = seconds

    def before_reply(self, model: str, hook: Callable[[], Awaitable[None]]) -> None:
        """Run ``hook`` once, the next time ``model`` is asked (to change things mid-call)."""
        self.hooks[model] = hook

    async def _handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/models"):
            listed = [{"id": model} for model in self.script]
            return httpx.Response(200, json={"object": "list", "data": listed})
        body = json.loads(request.content)
        model = str(body["model"])
        self.requests.append(SentRequest(request.url.host, model, body, dict(request.headers)))
        if model in self.delays:
            await asyncio.sleep(self.delays[model])
        if model in self.hooks:
            await self.hooks.pop(model)()
        queued = self.script.get(model)
        if not queued:
            raise AssertionError(f"FakeLLM: no reply scripted for {model!r}")
        reply = queued.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def sent_text(self) -> str:
        """Every request body as one string, for "this never reached the provider" checks."""
        return "\n".join(json.dumps(sent.body) for sent in self.requests)


@dataclass(frozen=True)
class SentRequest:
    host: str
    model: str
    body: dict[str, Any]
    headers: dict[str, str]


def ok(text: str, *, input_tokens: int = 12, output_tokens: int = 5) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": input_tokens, "completion_tokens": output_tokens},
        },
    )


def rate_limited(retry_after: float | None = None) -> httpx.Response:
    headers = {} if retry_after is None else {"Retry-After": str(retry_after)}
    return httpx.Response(429, headers=headers, json={"error": {"message": "quota"}})


def server_error() -> httpx.Response:
    return httpx.Response(503, json={"error": {"message": "overloaded"}})


def unauthorized() -> httpx.Response:
    return httpx.Response(401, json={"error": {"message": "bad key"}})


def refuse_network(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"A test tried to reach a real AI provider ({request.url.host})")
