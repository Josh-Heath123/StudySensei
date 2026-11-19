"""The real model separates teaching passages from the rest, and the default never links noise.

The synthetic fixtures are short passages, so they score lower than real slides: they were
calibrated at 0.63 (teaching 0.63-0.90, others 0.41-0.62). The default threshold has since
been raised to 0.75 from COS330 (evals/linking), where every similarity link scored 0.67 or
more. So the fixtures check the model's separation at their own threshold, and that no
unrelated passage reaches the default.
"""

import pytest

from app.core.config import get_settings
from app.services.search.embedding import get_embedder
from app.services.topic_maps.linking import topic_text
from tests.topic_maps.linking_fixtures import TOPICS, UNRELATED

FIXTURE_THRESHOLD = 0.63


@pytest.mark.real_embedder
def test_the_model_separates_each_topics_passages_from_the_others() -> None:
    embedder = get_embedder()
    default = get_settings().topic_link_threshold
    assert default >= FIXTURE_THRESHOLD
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
                assert score >= FIXTURE_THRESHOLD, (name, text[:40], score)
            else:
                assert score < FIXTURE_THRESHOLD, (name, text[:40], score)
                assert score < default, (name, text[:40], score)
