"""The topic schemas clip what can be clipped and reject only broken structure (ADR 0007)."""

import json

import pytest
from pydantic import ValidationError

from app.schemas.topic_maps import MaterialTopics, ModuleTopicMap, clip, read_pages


def test_long_names_and_descriptions_are_clipped_at_a_word() -> None:
    topics = MaterialTopics.model_validate(
        {"topics": [{"name": "Access control " * 10, "description": "word " * 100}]}
    )

    topic = topics.topics[0]
    assert len(topic.name) <= 80 and topic.name.endswith("…")
    assert topic.name.startswith("Access control Access control")
    assert not topic.name[:-1].endswith(" ")
    assert len(topic.description) <= 300


def test_only_the_first_ten_subtopics_are_kept() -> None:
    subtopics = [{"name": f"Sub {n}", "pages": [n]} for n in range(1, 15)]

    topic = MaterialTopics.model_validate({"topics": [{"name": "T", "subtopics": subtopics}]})

    assert [s.name for s in topic.topics[0].subtopics] == [f"Sub {n}" for n in range(1, 11)]


def test_a_third_level_is_folded_into_its_parent() -> None:
    data = {
        "topics": [
            {
                "name": "Firewalls",
                "pages": [1],
                "subtopics": [
                    {
                        "name": "Packet filters",
                        "pages": [2],
                        "subtopics": [{"name": "Stateless", "pages": [3, "4-5"]}],
                    }
                ],
            }
        ]
    }

    sub = MaterialTopics.model_validate(data).topics[0].subtopics[0]

    assert sub.name == "Packet filters"
    assert sub.pages == [2, 3, 4, 5]
    assert "subtopics" not in sub.model_dump()


@pytest.mark.parametrize(
    ("written", "pages"),
    [
        ([1, 2, 2], [1, 2]),
        (["3", "5-7"], [3, 5, 6, 7]),
        ("pp. 4, 6", [4, 6]),
        (["12 to 13", 0, -1, True], [12, 13]),
        ([2.0, "page 9" + chr(0x2013) + "10"], [2, 9, 10]),  # an en dash
        (None, []),
    ],
)
def test_page_numbers_are_read_however_they_were_written(written: object, pages: list[int]) -> None:
    assert read_pages(written) == pages


def test_a_missing_description_and_bare_strings_are_accepted() -> None:
    topics = MaterialTopics.model_validate(["Hashing", {"name": "Salts", "subtopics": ["Pepper"]}])

    assert [t.name for t in topics.topics] == ["Hashing", "Salts"]
    assert topics.topics[1].subtopics[0].name == "Pepper"
    assert topics.topics[0].description == ""


def test_too_many_topics_keep_the_first_forty() -> None:
    topics = MaterialTopics.model_validate({"topics": [f"T{n}" for n in range(60)]})

    assert len(topics.topics) == 40


@pytest.mark.parametrize(
    "reply",
    [
        '{"topics": "Passwords, sessions"}',
        '{"topics": [{"description": "no name"}]}',
        '{"topics": [{"name": ""}]}',
        '{"chapters": []}',
        "[1, 2, 3]",
    ],
)
def test_broken_structure_is_still_rejected(reply: str) -> None:
    with pytest.raises(ValidationError):
        MaterialTopics.model_validate_json(reply)


def test_the_merge_schema_is_lenient_the_same_way() -> None:
    tree = ModuleTopicMap.model_validate(
        {
            "topics": [
                {
                    "name": "Ch9 Firewalls " + "x" * 100,
                    "existing": 3,
                    "sources": "M1.1",
                    "subtopics": [{"name": f"S{n}", "sources": [f"M1.{n}"]} for n in range(20)]
                    + [],
                },
                {
                    "name": "Ch10 IDS",
                    "subtopics": [
                        {"name": "Rules", "subtopics": [{"name": "x", "sources": ["M2.1.1"]}]}
                    ],
                },
            ]
        }
    )

    first, second = tree.topics
    assert len(first.name) <= 80 and first.existing == "3" and first.sources == ["M1.1"]
    assert len(first.subtopics) == 15
    assert second.subtopics[0].sources == ["M2.1.1"]
    assert json.loads(tree.model_dump_json())  # round-trips


def test_clip_leaves_short_text_alone() -> None:
    assert clip("  Access   control ", 80) == "Access control"
