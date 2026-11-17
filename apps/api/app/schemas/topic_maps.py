"""Topic maps (decisions 0006, 0007): the AI's output shapes, and the API's responses.

AI output is saved only after it passes these models. They are lenient about what can be
fixed without guessing (decision 0007): over-long names and descriptions are clipped,
extra subtopics or topics beyond the limits are dropped (the first ones are kept), a third
level is folded into its parent, and page numbers written as "3", "3-5" or "p. 4" are read.
Only a reply whose structure is broken (not JSON, no list of topics, a topic with no name)
fails validation and gets the one repair attempt.
"""

import re
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

NAME_CHARS = 80
DESCRIPTION_CHARS = 300
MAX_PAGES = 200
MAX_TOPICS = 40
MAX_SUBTOPICS = 10
MAX_MERGED_TOPICS = 25
MAX_MERGED_SUBTOPICS = 15
# Hyphen, en dash, em dash or "to".
EN_DASH, EM_DASH = chr(0x2013), chr(0x2014)
_RANGE = re.compile(rf"(\d+)\s*(?:-|{EN_DASH}|{EM_DASH}|to)\s*(\d+)")
_NUMBER = re.compile(r"\d+")


def clip(text: Any, limit: int) -> str:
    """Whitespace collapsed, cut at a word boundary with "…" if it's longer than ``limit``."""
    collapsed = " ".join(str(text if text is not None else "").split())
    if len(collapsed) <= limit:
        return collapsed
    cut = collapsed[: limit - 1]
    if " " in cut[limit // 2 :]:
        cut = cut[: cut.rindex(" ")]
    return cut.rstrip(" ,;:-" + EN_DASH) + "…"


def read_pages(value: Any) -> list[int]:
    """Page numbers from what models actually write: ints, "3", "3-5", "pp. 4, 6", [..]."""
    items = value if isinstance(value, list) else [value]
    pages: list[int] = []
    for item in items:
        if isinstance(item, bool):
            continue
        if isinstance(item, int | float) and float(item).is_integer():
            pages.append(int(item))
        elif isinstance(item, str):
            for first, last in _RANGE.findall(item):
                low, high = int(first), int(last)
                if 0 < high - low <= MAX_PAGES:
                    pages.extend(range(low, high + 1))
            pages.extend(int(n) for n in _NUMBER.findall(_RANGE.sub(" ", item)))
    return list(dict.fromkeys(n for n in pages if n >= 1))[:MAX_PAGES]


# Keys models use for a topic's name instead of "name", in the order they're tried. The
# COS330 run's failures were topics and subtopics with no "name" at all (ADR 0008).
NAME_KEYS = ("title", "topic", "topic_name", "subtopic", "subtopic_name", "heading", "label")


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _as_node(value: Any) -> Any:
    """A bare string where a topic was expected is its name; a "title" (or similar) is too."""
    if isinstance(value, str):
        return {"name": value}
    if isinstance(value, dict) and not _has_text(value.get("name")):
        for key in NAME_KEYS:
            if _has_text(value.get(key)):
                return {**value, "name": value[key]}
    return value


def _fold_children(node: dict[str, Any], key: str) -> None:
    """A level deeper than allowed: its pages or sources join the parent, and it goes."""
    for child in node.pop("subtopics", None) or []:
        child = _as_node(child)
        if isinstance(child, dict):
            child = dict(child)
            _fold_children(child, key)
            node[key] = [*(node.get(key) or []), *(child.get(key) or [])]


class _Node(BaseModel):
    name: str = Field(min_length=1, max_length=NAME_CHARS)
    description: str = Field(default="", max_length=DESCRIPTION_CHARS)

    @field_validator("name", mode="before")
    @classmethod
    def _clip_name(cls, value: Any) -> Any:
        return clip(value, NAME_CHARS) if isinstance(value, str) else value

    @field_validator("description", mode="before")
    @classmethod
    def _clip_description(cls, value: Any) -> str:
        return clip(value, DESCRIPTION_CHARS)


# --- extract_topics: one material ---------------------------------------------------


class ProposedSubtopic(_Node):
    pages: list[int] = Field(
        default_factory=list, description="Page numbers in this material that cover it."
    )

    @field_validator("pages", mode="before")
    @classmethod
    def _read_pages(cls, value: Any) -> list[int]:
        return read_pages(value)

    @model_validator(mode="before")
    @classmethod
    def _two_levels(cls, data: Any) -> Any:
        data = _as_node(data)
        if isinstance(data, dict) and "subtopics" in data:
            data = dict(data)
            data["pages"] = read_pages(data.get("pages") or [])
            _fold_children(data, "pages")
        return data


class ProposedTopic(ProposedSubtopic):
    subtopics: list[ProposedSubtopic] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _two_levels(cls, data: Any) -> Any:
        return _as_node(data)

    @field_validator("subtopics", mode="before")
    @classmethod
    def _first_ten(cls, value: Any) -> Any:
        return value[:MAX_SUBTOPICS] if isinstance(value, list) else value


class MaterialTopics(BaseModel):
    """What one material covers: topics, each with at most 10 subtopics (two levels)."""

    topics: list[ProposedTopic]

    @model_validator(mode="before")
    @classmethod
    def _topics(cls, data: Any) -> Any:
        if isinstance(data, list):
            data = {"topics": data}
        if isinstance(data, dict) and isinstance(data.get("topics"), list):
            data = {**data, "topics": data["topics"][:MAX_TOPICS]}
        return data


# --- merge_topics: one module -------------------------------------------------------


def _refs(value: Any) -> list[str]:
    items = value if isinstance(value, list) else [value]
    return list(dict.fromkeys(str(item).strip() for item in items if str(item).strip()))[:200]


class MergedSubtopic(_Node):
    existing: str | None = Field(
        default=None, description='An existing topic\'s id ("E3") when this node is it.'
    )
    sources: list[str] = Field(
        default_factory=list,
        description='The proposal ids ("M2.3", "M2.3.1") merged into this node.',
    )

    @field_validator("existing", mode="before")
    @classmethod
    def _existing(cls, value: Any) -> str | None:
        text = str(value).strip() if value is not None else ""
        return text[:20] or None

    @field_validator("sources", mode="before")
    @classmethod
    def _read_refs(cls, value: Any) -> list[str]:
        return _refs(value) if value is not None else []

    @model_validator(mode="before")
    @classmethod
    def _two_levels(cls, data: Any) -> Any:
        data = _as_node(data)
        if isinstance(data, dict) and "subtopics" in data:
            data = dict(data)
            data["sources"] = _refs(data.get("sources") or [])
            _fold_children(data, "sources")
        return data


class MergedTopic(MergedSubtopic):
    subtopics: list[MergedSubtopic] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _two_levels(cls, data: Any) -> Any:
        return _as_node(data)

    @field_validator("subtopics", mode="before")
    @classmethod
    def _first_ones(cls, value: Any) -> Any:
        return value[:MAX_MERGED_SUBTOPICS] if isinstance(value, list) else value


class ModuleTopicMap(BaseModel):
    """The module's tree: chapters or big themes at the top, subtopics under each."""

    topics: list[MergedTopic]

    @model_validator(mode="before")
    @classmethod
    def _topics(cls, data: Any) -> Any:
        if isinstance(data, list):
            data = {"topics": data}
        if isinstance(data, dict) and isinstance(data.get("topics"), list):
            data = {**data, "topics": data["topics"][:MAX_MERGED_TOPICS]}
        return data


# --- API ---------------------------------------------------------------------------


class TopicMapStatus(BaseModel):
    # Materials whose topics can be extracted (allow_ai on, and a kind that teaches).
    eligible: int
    # Of those, how many have a proposal.
    analysed: int
    # extract_topics jobs waiting or running for the module.
    pending: int
    # Eligible materials whose last extraction failed for good.
    failed: int
    # A merge_topics job is waiting or running.
    merging: bool
    # When a job held back by AI rate limits or quotas will next run, if any.
    waiting_until: datetime | None
    # The latest failure's message (safe to show), if any.
    last_error: str | None
    # When the module's topics were last merged from proposals.
    merged_at: datetime | None


TopicState = Literal["analysed", "failed", "waiting"]


class ClearedTopics(BaseModel):
    # AI topics deleted; the student's own topics (and edited AI ones) are kept.
    deleted: int


class MaterialTopicStatus(BaseModel):
    """Where one eligible material's topic extraction stands (the Materials tab)."""

    material_id: uuid.UUID
    # analysed: it has a proposal; failed: its last run gave up (see error); waiting:
    # queued, running, held back by rate limits, or not started yet.
    state: TopicState
    error: str | None
    # "provider/model" that answered, once analysed.
    model: str | None
    # Top-level topics found.
    topics: int
