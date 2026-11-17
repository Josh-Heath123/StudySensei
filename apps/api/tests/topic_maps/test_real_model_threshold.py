"""The similarity threshold separates teaching passages from the rest, with the real model."""

import pytest

from app.core.config import get_settings
from app.services.search.embedding import get_embedder
from app.services.topic_maps.linking import topic_text
from tests.topic_maps.linking_fixtures import TOPICS, UNRELATED


@pytest.mark.real_embedder
def test_the_link_threshold_separates_each_topics_passages_from_the_others() -> None:
    embedder = get_embedder()
    threshold = get_settings().topic_link_threshold
    passages: list[tuple[str | None, str]] = [
        (name, text) for name, (_, texts) in TOPICS.items() for text in texts
    ]
    passages += [(None, text) for text in UNRELATED]
    vectors = embedder.embed_passages([text for _, text in passages])

    for name, (description, _) in TOPICS.items():
        query = embedder.embed_query(topic_text(name, description))
        for (owner, text), vector in zip(passages, vectors, strict=True):
            score = sum(a * b for a, b in zip(query, vector, strict=True))
            if owner == name:
                assert score >= threshold, (name, text[:40], score)
            else:
                assert score < threshold, (name, text[:40], score)
