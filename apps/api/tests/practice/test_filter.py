"""The generated-item filter and the AI schema's normalisation (ADR 0025). Pure."""

from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.practice import GeneratedItem, GeneratedPractice
from app.services.practice.filter import filter_items, prompt_key

LABELS = ["S1", "S2", "S3"]


def item(**kw: Any) -> GeneratedItem:
    base: dict[str, Any] = {
        "kind": "flashcard",
        "prompt": "What does a salt protect against?",
        "answer": "Precomputed (rainbow table) attacks.",
        "sources": ["S1"],
    }
    return GeneratedItem.model_validate({**base, **kw})


def test_labels_are_normalised_like_the_quizs() -> None:
    assert item(sources=["[S1]", "【S2】", "s3", " S1 "]).sources == ["S1", "S2", "S3", "S1"]
    # Anything else is kept as written, and won't match a source.
    assert item(sources=["Source 1"]).sources == ["Source 1"]


def test_the_schema_bounds() -> None:
    GeneratedPractice.model_validate({"items": [item().model_dump()] * 12})
    with pytest.raises(ValidationError):
        GeneratedPractice.model_validate({"items": [item().model_dump()] * 13})
    with pytest.raises(ValidationError):
        GeneratedPractice.model_validate({"items": []})
    with pytest.raises(ValidationError):
        item(prompt="x" * 501)
    with pytest.raises(ValidationError):
        item(answer="x" * 1501)
    with pytest.raises(ValidationError):
        item(key_points=["a", "b", "c", "d", "e", "f"])
    with pytest.raises(ValidationError):
        item(sources=[])
    with pytest.raises(ValidationError):
        item(kind="essay")
    # Extra keys are ignored; strings are stripped.
    assert item(prompt="  What is a nonce for?  ", extra=1).prompt == "What is a nonce for?"


def test_prompt_key_ignores_case_and_spacing() -> None:
    assert prompt_key("What is  a\nSalt?") == prompt_key("what is a salt?")
    assert prompt_key("What is a salt?") != prompt_key("What is a salt")
    assert len(prompt_key("x")) == 64


def test_each_reason_is_counted_once() -> None:
    items = [
        item(),  # kept
        item(prompt="Name the hash used here", sources=["S4"]),  # not_grounded
        item(prompt="Short?"),  # too_short (prompt under 8)
        item(prompt="Define a nonce briefly", answer="x"),  # too_short (answer under 2)
        item(prompt="Define a digest.", answer="define a DIGEST"),  # answer_repeats_prompt
        item(kind="short_answer", prompt="Why are salts unique per user?"),  # missing_key_points
        item(kind="short_answer", prompt="Why salt?? Explain", key_points=[]),  # missing
        item(prompt="what does a  SALT protect against?"),  # duplicate within the batch
        item(prompt="An already stored prompt"),  # duplicate of an existing item
        item(
            kind="short_answer",
            prompt="Compare MD5 and SHA-256 for password storage.",
            key_points=["Both are fast", "Neither should be used alone"],
            sources=["S2", "S3"],
        ),  # kept
    ]
    result = filter_items(
        items, labels=LABELS, existing_keys={prompt_key("An already stored prompt")}
    )
    assert [i.prompt for i in result.kept] == [
        "What does a salt protect against?",
        "Compare MD5 and SHA-256 for password storage.",
    ]
    assert result.dropped == {
        "not_grounded": 1,
        "too_short": 2,
        "answer_repeats_prompt": 1,
        "missing_key_points": 2,
        "duplicate": 2,
    }


def test_a_dropped_item_doesnt_claim_its_prompt() -> None:
    """An ungrounded item with a prompt doesn't make a later, grounded one a duplicate."""
    first = item(sources=["S9"])
    second = item()
    result = filter_items([first, second], labels=LABELS, existing_keys=set())
    assert result.kept == [second]
    assert result.dropped == {"not_grounded": 1}


def test_one_bad_label_among_good_ones_is_not_grounded() -> None:
    result = filter_items([item(sources=["S1", "S7"])], labels=LABELS, existing_keys=set())
    assert result.kept == [] and result.dropped == {"not_grounded": 1}
