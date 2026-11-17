"""Chat messages for the LLM client, and their OpenAI-compatible wire form."""

import base64
from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class Image:
    """An image sent inline (a scanned page, for example)."""

    data: bytes
    mime_type: str = "image/png"

    def data_url(self) -> str:
        return f"data:{self.mime_type};base64,{base64.b64encode(self.data).decode('ascii')}"


@dataclass(frozen=True)
class Message:
    role: Role
    text: str
    images: tuple[Image, ...] = field(default=())


def system(text: str) -> Message:
    return Message("system", text)


def user(text: str, *images: Image) -> Message:
    return Message("user", text, images)


def assistant(text: str) -> Message:
    return Message("assistant", text)


def has_images(messages: list[Message]) -> bool:
    return any(message.images for message in messages)


def to_wire(message: Message) -> dict[str, Any]:
    """The chat-completions form: plain text, or content parts when there are images."""
    if not message.images:
        return {"role": message.role, "content": message.text}
    parts: list[dict[str, Any]] = [{"type": "text", "text": message.text}]
    parts += [
        {"type": "image_url", "image_url": {"url": image.data_url()}} for image in message.images
    ]
    return {"role": message.role, "content": parts}
