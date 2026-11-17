"""Combine the topics found in a long material's parts into one proposal (decision 0007)."""

from collections.abc import Sequence
from typing import Any

from app.schemas.topic_maps import MAX_SUBTOPICS, MAX_TOPICS, MaterialTopics
from app.services.topic_maps.merge import name_key


def combine_parts(parts: Sequence[MaterialTopics]) -> MaterialTopics:
    """One topic list from several, in reading order.

    A topic named the same in two parts (case, spacing and punctuation ignored) becomes one:
    its pages are joined and its subtopics merged the same way. The limits still apply.
    """
    topics: dict[str, dict[str, Any]] = {}
    for part in parts:
        for topic in part.topics:
            key = name_key(topic.name)
            found = topics.get(key)
            if found is None:
                topics[key] = {
                    **topic.model_dump(exclude={"subtopics"}),
                    "subtopics": {name_key(s.name): s.model_dump() for s in topic.subtopics},
                }
                continue
            found["pages"] = list(dict.fromkeys([*found["pages"], *topic.pages]))
            found["description"] = found["description"] or topic.description
            for sub in topic.subtopics:
                existing = found["subtopics"].get(name_key(sub.name))
                if existing is None:
                    found["subtopics"][name_key(sub.name)] = sub.model_dump()
                else:
                    existing["pages"] = list(dict.fromkeys([*existing["pages"], *sub.pages]))
    return MaterialTopics.model_validate(
        {
            "topics": [
                {**topic, "subtopics": list(topic["subtopics"].values())[:MAX_SUBTOPICS]}
                for topic in list(topics.values())[:MAX_TOPICS]
            ]
        }
    )
